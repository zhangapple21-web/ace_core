from pathlib import Path
import shutil

REPO = Path(r"C:\tmp\ace_core")


def seed_owners_table(root: Path) -> None:
    """Give the fixture the real OWNERS table.

    The adjudication window writes its receipt into 08_GOVERNANCE, which is a
    governance-lane hotspot by the real table. A fixture without it leaves that
    region unowned, and the fail-closed default refuses the write - a failure
    that looks like a defect in the window and is really an empty fixture.
    """
    target = root / "04_PROTOCOLS"
    if target.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    source = REPO / "04_PROTOCOLS" / "LANE_OWNERS.json"
    if source.is_file():
        shutil.copy2(source, target / "LANE_OWNERS.json")