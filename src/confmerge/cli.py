"""Interfaccia a riga di comando (Fase 1): analyze / export / run."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, paths
from .ffmpeg_wrapper import Cancelled, FFmpegError
from .media_scan import media_info, pick_external_audio, scan_folder
from .pipeline import AnalysisReport, analyze, export
from .project import Project


def fmt_t(s: float) -> str:
    s = max(0.0, s)
    return f"{int(s // 3600):d}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def parse_t(text: str) -> float:
    """Accetta secondi (90.5) oppure [h:]mm:ss(.ms)."""
    parts = [float(x) for x in text.split(":")]
    t = 0.0
    for x in parts:
        t = t * 60 + x
    return t


def _progress(msg: str, frac: float) -> None:
    print(f"\r[{frac * 100:3.0f}%] {msg:<50}", end="", flush=True)
    if frac >= 1.0:
        print()


def _inputs_from_args(args) -> tuple[list[Path], Path]:
    if args.input and Path(args.input[0]).is_dir():
        scan = scan_folder(args.input[0])
        if not scan.videos:
            raise FFmpegError("Nessun video MP4/MOV trovato nella cartella")
        audio = Path(args.audio) if args.audio else pick_external_audio(scan.audios)
        if audio is None:
            raise FFmpegError("Nessun file audio esterno trovato nella cartella (usa --audio)")
        return scan.videos, audio
    if not args.audio:
        raise FFmpegError("Specifica l'audio esterno con --audio")
    return [Path(p) for p in args.input], Path(args.audio)


def print_report(rep: AnalysisReport) -> None:
    p = rep.project
    print(f"\nVideo ({len(rep.clips)}), ordinati per {rep.order_method}:")
    for c in rep.clips:
        rot = f" rot={c.rotation}°" if c.rotation else ""
        print(f"  {c.name}  {fmt_t(c.duration)}  {c.width}x{c.height}@{c.fps:.2f} {c.vcodec}{rot}")
    print(f"Durata totale: {fmt_t(p.total_duration)}")
    print(f"Audio esterno: {Path(p.audio).name}")
    side = "dopo" if p.offset_s > 0 else "prima"
    print(f"Offset: {p.offset_s * 1000:+.1f} ms (l'audio esterno parte {side} del video), confidenza {p.sync_confidence:.1f}")
    if p.drift_s is not None:
        print(f"Deriva: {p.drift_s * 1000:+.1f} ms, atempo={p.atempo:.8f}")
    if p.suggested_start is not None:
        print(f"Taglio suggerito: {fmt_t(p.suggested_start)} → {fmt_t(p.suggested_end)} (NON applicato)")
    for w in rep.warnings:
        print(f"ATTENZIONE: {w}")


def _cmd_analyze(args) -> int:
    videos, audio = _inputs_from_args(args)
    rep = analyze(videos, audio, _progress)
    print_report(rep)
    if args.output:
        rep.project.save(args.output)
        print(f"\nProgetto salvato in {args.output}")
    return 0


def _apply_trim(proj: Project, args) -> tuple[float | None, float | None]:
    t0 = parse_t(args.start) if args.start else None
    t1 = parse_t(args.end) if args.end else None
    if args.accept_trim:
        t0 = proj.suggested_start if t0 is None else t0
        t1 = proj.suggested_end if t1 is None else t1
    return t0, t1


def _cmd_export(args) -> int:
    proj = Project.load(args.project)
    return _do_export(proj, args)


def _do_export(proj: Project, args, clips=None) -> int:
    if args.drift_correct:
        if proj.offset_corrected_s is None:
            print("Deriva non misurata: correzione non disponibile", file=sys.stderr)
            return 2
        proj.use_drift_correction = True
    clips = clips or [media_info(c) for c in proj.clips]
    t0, t1 = _apply_trim(proj, args)
    started = time.time()

    def prog(frac: float, speed: float | None) -> None:
        eta = (time.time() - started) * (1 - frac) / frac if frac > 0.01 else 0
        sp = f" {speed:.1f}x" if speed else ""
        print(f"\r[{frac * 100:5.1f}%]{sp} residuo ~{eta:4.0f}s", end="", flush=True)

    plan = export(proj, clips, Path(args.out), args.mode, t0, t1, prog)
    print(f"\nModalità: {'copia stream' if plan.mode == 'copy' else 'ricodifica'}; "
          f"inizio {fmt_t(plan.start)}, durata {fmt_t(plan.duration)}")
    for n in plan.notes:
        print("NOTA:", n)
    size = Path(args.out).stat().st_size / 1e6
    print(f"Creato {args.out} ({size:.1f} MB) in {time.time() - started:.0f}s")
    return 0


def _cmd_run(args) -> int:
    videos, audio = _inputs_from_args(args)
    rep = analyze(videos, audio, _progress)
    print_report(rep)
    if args.save_project:
        rep.project.save(args.save_project)
    if rep.project.suggested_start is not None and not (args.accept_trim or args.start or args.end) and sys.stdin.isatty():
        ans = input("Applicare il taglio suggerito? [s/N] ").strip().lower()
        args.accept_trim = ans in ("s", "si", "sì", "y")
    return _do_export(rep.project, args, rep.clips)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="confmerge", description="ConfMerge – pipeline da riga di comando")
    ap.add_argument("--version", action="version", version=f"ConfMerge {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def inputs(p):
        p.add_argument("input", nargs="+", help="una cartella oppure uno o più file video")
        p.add_argument("--audio", help="audio esterno (se omesso con una cartella: il file più lungo)")

    def export_opts(p):
        p.add_argument("-o", "--out", required=True, help="file MP4 di uscita")
        p.add_argument("--mode", choices=["auto", "copy", "encode"], default="auto")
        p.add_argument("--start", help="inizio taglio (s o mm:ss)")
        p.add_argument("--end", help="fine taglio (s o mm:ss)")
        p.add_argument("--accept-trim", action="store_true", help="applica il taglio suggerito")
        p.add_argument("--drift-correct", action="store_true", help="applica la correzione di deriva (atempo)")

    a = sub.add_parser("analyze", help="analizza e (opz.) salva il progetto")
    inputs(a)
    a.add_argument("-o", "--output", help="salva il progetto .confmerge")
    a.set_defaults(func=_cmd_analyze)

    e = sub.add_parser("export", help="esporta da un progetto .confmerge")
    e.add_argument("project")
    export_opts(e)
    e.set_defaults(func=_cmd_export)

    r = sub.add_parser("run", help="analizza ed esporta")
    inputs(r)
    export_opts(r)
    r.add_argument("--save-project")
    r.set_defaults(func=_cmd_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_file = paths.setup_logging(args.verbose)
    try:
        return args.func(args)
    except Cancelled:
        print("\nAnnullato.")
        return 130
    except (FFmpegError, ValueError, OSError) as e:
        print(f"\nErrore: {e}\n(log: {log_file})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
