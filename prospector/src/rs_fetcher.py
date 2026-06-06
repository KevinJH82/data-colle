"""遥感资料获取器 — Sentinel-2 / Landsat / ASTER 影像检索"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote, urlencode

from .logger import get_logger
from .roi_parser import get_bbox_tuple
from config import STAC_API_URL, EE_URL, GS_CLOUD_URL

logger = get_logger("rs")


def search_sentinel2(
    roi: Dict[str, Any],
    max_cloud_cover: int = 10,
    max_items: int = 5,
    date_range: str = "2022-01-01/2026-06-01",
) -> List[Dict[str, Any]]:
    """
    使用 STAC API 检索 Sentinel-2 影像

    Args:
        roi: parse_roi + expand_bbox 的输出
        max_cloud_cover: 最大云覆盖率 (%)
        max_items: 最多返回条数
        date_range: 日期范围 "YYYY-MM-DD/YYYY-MM-DD"

    Returns:
        [{id, date, cloud_cover, thumbnail, download_url, ...}]
    """
    bbox = get_bbox_tuple(roi, use_expanded=True)

    try:
        from pystac_client import Client

        catalog = Client.open(f"{STAC_API_URL}")
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
            max_items=max_items,
        )

        items = []
        for item in search.items():
            items.append({
                "id": item.id,
                "date": item.datetime.isoformat() if item.datetime else None,
                "cloud_cover": item.properties.get("eo:cloud_cover", "N/A"),
                "platform": item.properties.get("platform", "sentinel-2"),
                "thumbnail": item.assets.get("thumbnail", {}).get("href", ""),
                "visual_url": item.assets.get("visual", {}).get("href", ""),
                "bbox": item.bbox,
            })

        logger.info("Sentinel-2: 检索到 %d 景影像 (云量<%d%%)", len(items), max_cloud_cover)
        return items

    except ImportError:
        logger.warning("pystac-client 未安装，生成手动检索链接")
        return []
    except Exception as e:
        logger.warning("Sentinel-2 STAC 检索失败: %s", e)
        return []


# ============================================================
# USGS EarthExplorer (Landsat / ASTER) — 链接生成
# ============================================================



def generate_earth_explorer_links(roi: Dict[str, Any]) -> List[Dict[str, str]]:
    """生成 USGS EarthExplorer 检索链接（无法自动下载，需生成链接）"""

    bbox = get_bbox_tuple(roi, use_expanded=True)

    # EarthExplorer 使用 URL fragment 不可直接传参，生成说明链接
    return [
        {
            "label": "USGS EarthExplorer — Landsat 8/9",
            "url": EE_URL,
            "note": (
                f"用多边形工具圈定 ROI 范围（{bbox[0]:.2f}E, {bbox[1]:.2f}N → "
                f"{bbox[2]:.2f}E, {bbox[3]:.2f}N），选择 Landsat 8-9 OLI/TIRS Collection 2 Level-2"
            ),
        },
        {
            "label": "USGS EarthExplorer — ASTER L1T",
            "url": EE_URL,
            "note": "ASTER 多光谱数据（14波段），适合蚀变矿物填图（羟基、铁染、碳酸盐）",
        },
    ]


# ============================================================
# 地理空间数据云 (中国镜像) — 链接生成
# ============================================================



def generate_gscloud_links(roi: Dict[str, Any]) -> List[Dict[str, str]]:
    """生成地理空间数据云检索链接"""
    return [
        {
            "label": "地理空间数据云 — Landsat 数据",
            "url": f"{GS_CLOUD_URL}sources/?cdataid=263",
            "note": "中科院维护，国内下载速度快，实名注册后免费下载",
        },
        {
            "label": "地理空间数据云 — DEM 数字高程数据",
            "url": f"{GS_CLOUD_URL}sources/?cdataid=302",
            "note": "SRTM 30m / GDEM 30m 数据",
        },
        {
            "label": "地理空间数据云 — ASTER 数据",
            "url": f"{GS_CLOUD_URL}sources/?cdataid=301",
            "note": "多光谱蚀变填图",
        },
    ]


# ============================================================
# ASTER 蚀变矿物填图 — 信息生成
# ============================================================

ASTER_BAND_INFO = """
ASTER 波段配置与蚀变矿物填图:
  VNIR (波段1-3):  15m 分辨率 → 铁染蚀变识别 (Fe³⁺ 吸收特征)
  SWIR (波段4-9):  30m 分辨率 → 羟基蚀变、碳酸盐化识别 (OH⁻, CO₃²⁻ 吸收特征)
  TIR  (波段10-14): 90m 分辨率 → 硅酸盐矿物识别 (Si-O 伸缩振动)

  关键波段比值:
  - 铁染: Band 2/Band 1 (氧化铁)
  - 羟基: (Band 4+Band 7)/(Band 6+Band 9) (绢云母、绿泥石、高岭石)
  - 碳酸盐: Band 13/Band 14
"""


def fetch_all_remote_sensing(
    roi: Dict[str, Any],
    output_dir: Path,
    mineral_info: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    获取所有遥感资料

    Returns:
        {
            "sentinel2": [...],
            "earth_explorer_links": [...],
            "gscloud_links": [...],
            "aster_info": str,
        }
    """
    logger.info("收集遥感资料...")

    results = {
        "sentinel2": search_sentinel2(roi),
        "earth_explorer_links": generate_earth_explorer_links(roi),
        "gscloud_links": generate_gscloud_links(roi),
        "aster_info": ASTER_BAND_INFO,
    }

    return results
