"""
shape_map.py — shape_id → JSONファイルパス 変換モジュール

使い方:
    from shape_map import shape_id_to_json, ASSETS_DIR

    path = shape_id_to_json(102)   # → ".../A_primitives/A_02.json"
    path = shape_id_to_json(9999)  # → None (未対応)
"""

from __future__ import annotations
from pathlib import Path

# assetsディレクトリ（このファイルと同階層の assets/ を基準とする）
ASSETS_DIR = Path(__file__).parent / "assets"

# 特例マッピング（shape_id末尾00のもの）
_SPECIAL: dict[int, tuple[str, str]] = {
    2000: ("T_font01_lowercase",  "T_01.json"),
    3000: ("PP_font07_lowercase", "PP_01.json"),
}

# 通常マッピング
# (start, end, folder, file_prefix, file_num_start)
# shape_id: start〜end → {folder}/{prefix}_{num:02d}.json
# num = file_num_start + (shape_id - start)
_RANGES: list[tuple[int, int, str, str, int]] = [
    # primitives & shapes
    (101,  140,  "A_primitives",          "A",  1),
    (201,  240,  "B_gradient_shapes",     "B",  1),
    (301,  340,  "C_stripes",             "C",  1),
    (401,  440,  "D_tears",               "D",  1),
    (501,  540,  "E_racing_icons",        "E",  1),
    (601,  640,  "F_flames",              "F",  1),
    (701,  740,  "G_paint_splats",        "G",  1),
    (801,  840,  "H_tribal",              "H",  1),
    (901,  940,  "I_nature",              "I",  1),
    # fonts uppercase
    (1301, 1340, "M_font02_uppercase",    "M",  1),
    (1501, 1540, "O_font03_uppercase",    "O",  1),
    (1701, 1740, "Q_font04_uppercase",    "Q",  1),
    (1901, 1940, "S_font01_uppercase",    "S",  1),
    (2501, 2540, "KK_font05_uppercase",   "KK", 1),
    (2701, 2740, "MM_font06_uppercase",   "MM", 1),
    (2901, 2940, "OO_font07_uppercase",   "OO", 1),
    (3101, 3140, "QQ_font08_uppercase",   "QQ", 1),
    (3301, 3340, "SS_font09_uppercase",   "SS", 1),
    (3501, 3540, "UU_font10_uppercase",   "UU", 1),
    (3701, 3740, "WW_font11_uppercase",   "WW", 1),
    # fonts lowercase
    (1401, 1440, "N_font02_lowercase",    "N",  1),
    (1601, 1640, "P_font03_lowercase",    "P",  1),
    (1801, 1840, "R_font04_lowercase",    "R",  1),
    (2002, 2040, "T_font01_lowercase",    "T",  2),  # T_02〜T_40
    (2601, 2640, "LL_font05_lowercase",   "LL", 1),
    (2801, 2840, "NN_font06_lowercase",   "NN", 1),
    (3002, 3040, "PP_font07_lowercase",   "PP", 2),  # PP_02〜PP_40
    (3201, 3240, "RR_font08_lowercase",   "RR", 1),
    (3401, 3440, "TT_font09_lowercase",   "TT", 1),
    (3601, 3640, "VV_font10_lowercase",   "VV", 1),
    (3801, 3840, "XX_font11_lowercase",   "XX", 1),
    # community vinyls (U/V は2フォルダに分割)
    (2101, 2140, "U_community_vinyls_01", "U",  1),   # U_01〜U_40
    (2201, 2240, "U_community_vinyls_02", "U", 41),   # U_41〜U_80
    (2301, 2340, "V_community_vinyls_03", "V",  1),   # V_01〜V_40
    (2401, 2440, "V_community_vinyls_04", "V", 51),   # V_51〜V_90
]


def shape_id_to_json(shape_id: int) -> Path | None:
    """
    shape_id からJSONファイルのPathを返す。
    対応するファイルが存在しない場合はNoneを返す。
    """
    # 特例
    if shape_id in _SPECIAL:
        folder, fname = _SPECIAL[shape_id]
        path = ASSETS_DIR / folder / fname
        return path if path.exists() else None

    # 通常マッピング
    for start, end, folder, prefix, file_num_start in _RANGES:
        if start <= shape_id <= end:
            file_num = file_num_start + (shape_id - start)
            fname    = f"{prefix}_{file_num:02d}.json"
            path     = ASSETS_DIR / folder / fname
            return path if path.exists() else None

    return None


def shape_id_to_json_str(shape_id: int) -> str | None:
    """shape_id からJSONファイルの文字列パスを返す。"""
    p = shape_id_to_json(shape_id)
    return str(p) if p else None


if __name__ == "__main__":
    # 動作確認
    tests = [
        (101, "A_01"), (102, "A_02"), (103, "A_03"),
        (701, "G_01"), (739, "G_39"),
        (2000, "T_01"), (2002, "T_02"),
        (2101, "U_01"), (2201, "U_41"),
        (2301, "V_01"), (2401, "V_51"),
        (3000, "PP_01"), (3002, "PP_02"),
        (3840, "XX_40"),
    ]
    print("shape_id → SVG マッピングテスト:")
    for sid, expected in tests:
        result = shape_id_to_json(sid)
        name   = result.name.replace(".json","") if result else "None"
        ok     = name == expected
        print(f"  {'✓' if ok else '✗'} {sid:5d} → {name:10s}  {'(exists)' if result and result.exists() else '(not found)'}")
