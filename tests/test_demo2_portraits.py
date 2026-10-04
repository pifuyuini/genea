"""Verify the independent public portraits without the original image matrices."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo2"


def jpeg_size(path):
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise AssertionError("Expected JPEG portrait")
    offset = 2
    while offset < len(data):
        marker = data[offset + 1]
        offset += 2
        length = int.from_bytes(data[offset:offset + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2}:
            return (int.from_bytes(data[offset + 5:offset + 7], "big"),
                    int.from_bytes(data[offset + 3:offset + 5], "big"))
        offset += length
    raise AssertionError("JPEG dimensions are missing")


class Demo2PortraitTests(unittest.TestCase):
    def test_public_manifest_and_46_portraits_match_the_workspace(self):
        manifest = json.loads((DEMO / "portraits/manifest.json").read_text(encoding="utf-8"))
        workspace = json.loads((DEMO / "data/workspace.json").read_text(encoding="utf-8"))
        entries = [entry for sheet in manifest["sheets"] for entry in sheet["portraits"]]
        self.assertEqual([len(sheet["portraits"]) for sheet in manifest["sheets"]], [16, 16, 14])
        self.assertEqual({entry["person_id"] for entry in entries}, set(workspace["people"]))
        self.assertEqual(len({entry["output_file"] for entry in entries}), 46)
        self.assertEqual({path.name for path in (DEMO / "data/photos").iterdir() if path.is_file()},
                         {entry["output_file"] for entry in entries})
        for sheet in manifest["sheets"]:
            self.assertFalse({(entry["row"], entry["column"]) for entry in sheet["portraits"]}
                             & {(cell["row"], cell["column"]) for cell in sheet["empty_cells"]})
        for entry in entries:
            self.assertEqual(workspace["people"][entry["person_id"]]["photo_path"],
                             "/photos/" + entry["output_file"])
            self.assertEqual(jpeg_size(DEMO / "data/photos" / entry["output_file"]), (256, 256))
        for index in range(1, 4):
            self.assertTrue((DEMO / "portraits" / f"prompt-{index:02d}.txt").is_file())


if __name__ == "__main__":
    unittest.main()
