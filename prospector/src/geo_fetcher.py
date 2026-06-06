"""地质资料获取器 — 地质图检索链接 / DEM / 学术文献"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from .logger import get_logger
from config import NGAC_SEARCH_PAGE, ONEGEOLOGY_URL

logger = get_logger("geo")


def _get_1m_map_sheet(roi: Dict[str, Any]) -> str:
    """
    根据经纬度推算 1:100万 图幅号（用于 NGAC 检索）
    中国 1:100万 图幅编号: 行(A-U) + 列(1-60)
    """
    center = roi['center']
    lat = center['lat']
    lon = center['lon']

    # 纬度行号 (从赤道开始，每4度一个字母，A=0-4°N)
    if lat < 0:
        letter_idx = int((-lat) / 4)
        row = chr(ord('A') + letter_idx)
        row = 'S' + row  # 南半球前缀
    else:
        letter_idx = int(lat / 4)
        if letter_idx > 21:
            letter_idx = 21
        row = chr(ord('A') + letter_idx)

    # 经度列号 (从180°W开始，每6度)
    col = int((lon + 180) / 6) + 1
    if col > 60:
        col = 60
    if col < 1:
        col = 1

    return f"{row}{col:02d}"


def generate_ngac_geology_links(roi: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    生成 NGAC 地质图检索链接
    """
    b = roi['bbox']
    map_sheet = _get_1m_map_sheet(roi)
    center = roi['center']

    links = [
        {
            "label": "全国地质资料馆 — 地质图检索入口",
            "url": NGAC_SEARCH_PAGE,
            "note": "NGAC 检索平台，进入后手动输入关键词搜索"
        },
        {
            "label": f"▶ 建议检索词: {map_sheet}",
            "url": NGAC_SEARCH_PAGE,
            "note": "1:100万 图幅号，含地质图+说明书"
        },
        {
            "label": "▶ 建议检索词: 区域地质调查报告 / 区域地质图 / 地质矿产图",
            "url": NGAC_SEARCH_PAGE,
            "note": f"ROI 中心: {center['lon']:.1f}°E, {center['lat']:.1f}°N"
        },
    ]

    return links


def generate_ngac_mineral_links(roi: Dict[str, Any], mineral: str) -> List[Dict[str, str]]:
    """生成矿产地 + 钻孔数据检索链接"""
    return [
        {
            "label": f"NGAC 矿产地: '{mineral}矿床' / '{mineral}矿产地'",
            "url": NGAC_SEARCH_PAGE,
            "note": "进入后搜索矿产地关键词"
        },
        {
            "label": "NGAC 钻孔数据库",
            "url": "https://www.ngac.cn/125cms/c/qggnew/zljs.htm",
            "note": "全国地质资料馆检索，含钻孔数据"
        },
    ]


def generate_ngac_geochem_links(roi: Dict[str, Any], mineral: str) -> List[Dict[str, str]]:
    """生成化探数据检索链接"""
    map_sheet = _get_1m_map_sheet(roi)

    return [
        {
            "label": f"NGAC 化探: {map_sheet} 图幅地球化学图",
            "url": NGAC_SEARCH_PAGE,
            "note": f"检索词: '{map_sheet} 地球化学' — 39种元素，1039张图件"
        },
        {
            "label": f"NGAC 化探: '{mineral}' 化探异常图",
            "url": NGAC_SEARCH_PAGE,
            "note": f"检索词: '{mineral} 化探异常'"
        },
        {
            "label": "国家级地质资料数据中心",
            "url": "https://www.ngac.cn",
            "note": "NGAC 门户，含化探/物探/遥感等公开数据，DOI: 10.23650/data.G.2018.NGA122099.K1.1.1.V1"
        },
    ]


# ============================================================
# 学术文献检索链接生成
# ============================================================

def generate_cnki_links(roi: Dict[str, Any], mineral: str,
                        mineral_info: Optional[Dict] = None,
                        location: Optional[Dict] = None) -> List[Dict[str, str]]:
    """
    生成 CNKI 学术文献检索链接（带构造单元/区域定位）
    """
    center = roi['center']

    # 构造区域关键词
    region_terms = []
    if location:
        tu = location.get('center_tectonic')
        if tu:
            region_terms.append(tu['name'])
        pb = location.get('petroleum_basin')
        if pb:
            region_terms.append(pb['name'])

    # 经纬度兜底
    region_terms.append(f"({center['lon']:.1f}E,{center['lat']:.1f}N)")

    links = []
    for term in region_terms[:2]:  # 取前2个最相关的区域词
        # CNKI
        su = f"{term} {mineral}矿 成矿 地质特征"
        links.append({
            "label": f"CNKI: [{term}] {mineral}矿床地质",
            "url": f"https://kns.cnki.net/kns8s/search?keyword={quote(su)}",
            "note": "按构造单元/盆地+矿种精准检索"
        })
        # 化探
        su2 = f"{term} {mineral} 化探 地球化学"
        links.append({
            "label": f"CNKI: [{term}] {mineral}化探异常",
            "url": f"https://kns.cnki.net/kns8s/search?keyword={quote(su2)}",
            "note": "检索该区域的化探研究成果"
        })

    # Google Scholar
    if location:
        tu = location.get('center_tectonic')
        if tu:
            en = tu.get('name_en', '')
            scholar_term = f"{mineral} deposit {en}"
            links.append({
                "label": f"Google Scholar: {scholar_term}",
                "url": f"https://scholar.google.com/scholar?q={quote(scholar_term)}",
                "note": "英文文献"
            })

    return links


def generate_onegeology_link(roi: Dict[str, Any]) -> str:
    """生成 OneGeology 全球地质图查看链接"""
    b = roi['bbox']
    return (
        f"{ONEGEOLOGY_URL}"
        f"?bbox={b['west']},{b['south']},{b['east']},{b['north']}"
    )


def fetch_all_geological(
    roi: Dict[str, Any],
    output_dir: Path,
    mineral: str,
    mineral_info: Optional[Dict] = None,
    location: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    获取所有地质资料（生成检索链接 + 元数据）

    Returns:
        {
            "ngac_geology": [...],
            "ngac_mineral": [...],
            "ngac_geochem": [...],
            "cnki": [...],
            "onegeology": "...",
            "map_sheet": str,
        }
    """
    logger.info("收集地质资料...")

    results = {
        "ngac_geology": generate_ngac_geology_links(roi),
        "ngac_mineral": generate_ngac_mineral_links(roi, mineral),
        "ngac_geochem": generate_ngac_geochem_links(roi, mineral),
        "cnki": generate_cnki_links(roi, mineral, mineral_info, location),
        "onegeology": generate_onegeology_link(roi),
        "map_sheet": _get_1m_map_sheet(roi),
    }

    n_links = (
        len(results["ngac_geology"]) +
        len(results["ngac_mineral"]) +
        len(results["ngac_geochem"]) +
        len(results["cnki"])
    )

    logger.info("生成 %d 个地质资料检索链接", n_links)
    logger.info("1:100万 图幅号: %s", results['map_sheet'])

    return results
