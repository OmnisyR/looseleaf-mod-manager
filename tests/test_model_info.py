from __future__ import annotations

import io
import struct
import unittest

from modmanager.model_info import compare_model_info, decode_model_info_json


def encode_test_bin_json(data: object) -> bytes:
    stream = io.BytesIO()
    string_offsets: dict[str, int] = {}

    def write_string(value: str, dictionary: bool = False) -> None:
        if dictionary:
            stream.write(b"\xff\xff\xff\xff")
        stream.write(value.encode("utf-8"))
        stream.write(b"\0")

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in string_offsets:
                    string_offsets[key] = stream.tell()
                    write_string(key, dictionary=True)
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    def value_kind(value: object) -> int:
        if value is None:
            return 0x01
        if isinstance(value, str):
            return 0x02
        if isinstance(value, bool):
            return 0x06
        if isinstance(value, (int, float)):
            return 0x03
        if isinstance(value, dict):
            return 0x04
        if isinstance(value, list):
            return 0x05
        raise TypeError(type(value))

    def write_payload(value: object) -> None:
        if value is None:
            return
        if isinstance(value, str):
            write_string(value)
        elif isinstance(value, bool):
            stream.write(struct.pack("<B", int(value)))
        elif isinstance(value, (int, float)):
            stream.write(struct.pack("<d", float(value)))
        elif isinstance(value, dict):
            keys = list(value.keys())
            stream.write(struct.pack("<I", len(keys)))
            address_table = stream.tell()
            stream.write(b"\0" * (4 * len(keys)))
            addresses: list[int] = []
            for key in keys:
                addresses.append(stream.tell())
                write_value(value[key], key)
            end = stream.tell()
            stream.seek(address_table)
            stream.write(struct.pack(f"<{len(addresses)}I", *addresses))
            stream.seek(end)
        elif isinstance(value, list):
            stream.write(struct.pack("<I", len(value)))
            address_table = stream.tell()
            stream.write(b"\0" * (4 * len(value)))
            addresses = []
            for child in value:
                addresses.append(stream.tell())
                write_value(child, None)
            end = stream.tell()
            stream.seek(address_table)
            stream.write(struct.pack(f"<{len(addresses)}I", *addresses))
            stream.seek(end)

    def write_value(value: object, name: str | None) -> None:
        kind = value_kind(value)
        stream.write(struct.pack("<B", kind if name is not None else kind | 0x10))
        if name is not None:
            stream.write(struct.pack("<I", string_offsets[name]))
        write_payload(value)

    stream.write(b"JSON\0\0\0\0" + b"\0" * 8)
    string_offsets[""] = stream.tell()
    write_string("", dictionary=True)
    collect_keys(data)
    data_start = stream.tell()
    stream.seek(8)
    stream.write(struct.pack("<Q", data_start))
    stream.seek(data_start)
    write_value(data, "")
    return stream.getvalue()


class ModelInfoDiffTests(unittest.TestCase):
    def test_binary_json_diff_reports_exact_dynamic_bone_values(self) -> None:
        original = encode_test_bin_json(
            {
                "DynamicBone": [
                    {
                        "Joint": [
                            {"node": "LeftBreast", "damping": 0.1, "gravity": -0.98},
                            {"node": "LeftBreast_Top", "resilience": 18, "rotation_limit": 0.314159},
                        ],
                    }
                ],
                "Locators": [],
            }
        )
        modified = encode_test_bin_json(
            {
                "DynamicBone": [
                    {
                        "Joint": [
                            {"node": "LeftBreast", "damping": 0.01, "gravity": -0.5},
                            {"node": "LeftBreast_Top", "resilience": 4.8, "rotation_limit": 0.45},
                        ],
                    }
                ],
                "Locators": [],
            }
        )

        self.assertEqual(decode_model_info_json(original)["DynamicBone"][0]["Joint"][0]["node"], "LeftBreast")
        diff = compare_model_info(original, modified).to_dict()

        self.assertEqual(diff["status"], "changed")
        self.assertEqual(diff["semantic_change_count"], 4)
        self.assertEqual(diff["changed_sections"], {"DynamicBone": 4})
        self.assertEqual(diff["impact_keys"], ["physics"])
        self.assertTrue(diff["parameter_only"])
        self.assertIn(
            {
                "path": "$.DynamicBone[0].Joint[0].damping",
                "change": "value_changed",
                "before": 0.1,
                "after": 0.01,
                "context": "LeftBreast",
            },
            diff["semantic_changes"],
        )

    def test_diff_reports_gameplay_impact_categories(self) -> None:
        original = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0DynamicBone\0Collider\0LeftBreast\0"
        modified = original + b"DynamicBoneCollider\0collision_radius\0RightBreast\0"

        diff = compare_model_info(original, modified).to_dict()

        self.assertEqual(diff["status"], "changed")
        self.assertIn("physics", diff["impact_keys"])
        self.assertIn("collision", diff["impact_keys"])
        self.assertIn("RightBreast", diff["notable_identifiers_added"])

    def test_parameter_only_change_is_called_out(self) -> None:
        original = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0DynamicBone\0LeftBreast\0\x01"
        modified = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0DynamicBone\0LeftBreast\0\x02"

        diff = compare_model_info(original, modified).to_dict()

        self.assertTrue(diff["parameter_only"])
        self.assertIn("physics", diff["impact_keys"])


if __name__ == "__main__":
    unittest.main()
