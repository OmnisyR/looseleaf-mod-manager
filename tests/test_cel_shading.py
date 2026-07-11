from __future__ import annotations

import copy
import unittest

from modmanager.cel_shading import (
    COPY_FIELDS,
    _apply_material_templates,
)


def material(
    name: str,
    marker: str,
    textures: list[dict],
    *,
    material_id: int,
    shader_name: str = "chr_skin",
) -> dict:
    return {
        "id_referenceonly": material_id,
        "material_name": name,
        "shader_name": shader_name,
        "str3": shader_name,
        "shader_switches_hash_referenceonly": f"hash-{marker}",
        "textures": copy.deepcopy(textures),
        "shaders": [{"shader_name": marker, "type_int": 0, "data": 1}],
        "material_switches": [{"material_switch_name": marker, "int2": -1}],
        "uv_map_indices": [marker],
        "unknown1": [marker, 1],
        "unknown2": [marker, 2],
    }


class CelShadingMaterialTests(unittest.TestCase):
    def test_face_uses_complete_official_material_while_body_keeps_mod_textures(self) -> None:
        mod_face_textures = [
            {"texture_image_name": "woman01_face", "texture_slot": 0},
            {"texture_image_name": "woman01_face_r_p", "texture_slot": 8},
            {"texture_image_name": "toon_skin", "texture_slot": 9},
        ]
        official_face_textures = [
            {"texture_image_name": "common_w01_face_c_q", "texture_slot": 0},
            {"texture_image_name": "common_w01_face_q", "texture_slot": 7},
            {"texture_image_name": "cheek_a_01", "texture_slot": 1},
            {"texture_image_name": "toon_chr02", "texture_slot": 9},
        ]
        official_face_02_textures = [
            {"texture_image_name": "common_w01_face_c_q", "texture_slot": 0},
            {"texture_image_name": "common_w01_face_q", "texture_slot": 7},
            {"texture_image_name": "toon_chr02", "texture_slot": 9},
        ]
        mod_body_textures = [
            {"texture_image_name": "custom_body", "texture_slot": 0},
            {"texture_image_name": "custom_body_n", "texture_slot": 3},
            {"texture_image_name": "custom_body_q", "texture_slot": 7},
            {"texture_image_name": "toon_skin", "texture_slot": 9},
        ]
        official_body_textures = [
            {"texture_image_name": "official_body", "texture_slot": 0},
            {"texture_image_name": "official_body_q", "texture_slot": 7},
            {"texture_image_name": "toon_chr01", "texture_slot": 9},
        ]

        targets = [
            material("face", "mod-face", mod_face_textures, material_id=10),
            material("face_02", "mod-face-02", mod_face_textures, material_id=11),
            material("body_skin", "mod-body", mod_body_textures, material_id=12),
            material("eyes", "mod-eyes", [], material_id=13, shader_name="chr_eye"),
            material("shadow", "mod-shadow", [], material_id=14, shader_name="chr_cloth"),
        ]
        templates = [
            material("face", "official-face", official_face_textures, material_id=0),
            material("face_02", "official-face-02", official_face_02_textures, material_id=1),
            material("body_skin", "official-body", official_body_textures, material_id=2),
            material("eyes", "official-eyes", [], material_id=3, shader_name="chr_eye"),
            material("shadow", "official-shadow", [], material_id=4, shader_name="chr_cloth"),
        ]
        original_eyes = copy.deepcopy(targets[3])
        original_shadow = copy.deepcopy(targets[4])

        changed = _apply_material_templates(targets, templates)

        self.assertEqual(changed, ["face", "face_02", "body_skin"])
        for target_index, template_index in ((0, 0), (1, 1)):
            target = targets[target_index]
            template = templates[template_index]
            self.assertEqual(target["id_referenceonly"], 10 + target_index)
            self.assertEqual(target["material_name"], template["material_name"])
            self.assertEqual(target["textures"], template["textures"])
            self.assertIsNot(target["textures"], template["textures"])
            for field in COPY_FIELDS:
                self.assertEqual(target[field], template[field])

        body_textures = targets[2]["textures"]
        self.assertEqual(
            [(texture["texture_slot"], texture["texture_image_name"]) for texture in body_textures],
            [(0, "custom_body"), (7, "custom_body_q"), (9, "toon_chr01")],
        )
        self.assertEqual(targets[2]["shaders"], templates[2]["shaders"])
        self.assertEqual(targets[3], original_eyes)
        self.assertEqual(targets[4], original_shadow)

    def test_second_application_is_idempotent(self) -> None:
        textures = [{"texture_image_name": "common_w01_face_c_q", "texture_slot": 0}]
        target = material("face", "mod-face", [], material_id=5)
        template = material("face", "official-face", textures, material_id=0)

        self.assertEqual(_apply_material_templates([target], [template]), ["face"])
        self.assertEqual(_apply_material_templates([target], [template]), [])


if __name__ == "__main__":
    unittest.main()
