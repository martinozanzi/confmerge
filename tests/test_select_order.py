import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg assente")


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    d = tmp_path_factory.mktemp("order")
    # i nomi sono in ordine opposto alle date: DJI_0001 è l'ULTIMO registrato
    for name, minute in (("DJI_0001.mp4", 30), ("DJI_0002.mp4", 20), ("DJI_0003.mp4", 10)):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=2",
                        "-metadata", f"creation_time=2026-05-01T10:{minute:02d}:00Z", "-c:v", "libx264", str(d / name)], check=True)
    return d


def names(page):
    return [p.name for p in page.videos]


def test_order_modes_and_numbering(qt_app, folder, tmp_path):
    from confmerge.settings import Settings
    from confmerge.ui.pages import SelectPage
    from confmerge.ui.state import AppState

    page = SelectPage(AppState(Settings(tmp_path)))
    page.load_folder(folder)
    # predefinito: per data di registrazione → il più vecchio (DJI_0003) è il PRIMO, in alto
    assert names(page) == ["DJI_0003.mp4", "DJI_0002.mp4", "DJI_0001.mp4"]
    assert page.list.item(0).text().startswith("1.  DJI_0003.mp4")
    assert "registrato il" in page.list.item(0).text()
    assert "diverso da quello per nome" in page.summary.text()          # avviso: data e nome non coincidono
    page.order_seg.setValue("name")
    page._order_changed("name")
    assert names(page) == ["DJI_0001.mp4", "DJI_0002.mp4", "DJI_0003.mp4"]
    page.list.setCurrentRow(0)
    page.move(1)                                                         # ▼ → passa a «Manuale»
    assert page.order_mode == "manual" and names(page)[1] == "DJI_0001.mp4"
    assert page.order_seg.value() == "manual"
