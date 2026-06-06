"""报告生成器 — ROI 针对性报告，非通用科普"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .logger import get_logger
from config import MYMEMORY_URL

logger = get_logger("report")


def _translate_en_to_cn(text: str) -> str:
    """将英文文本翻译为中文，失败时返回原文"""
    if not text or not text.strip():
        return text

    # 纯中文直接返回
    if len([c for c in text if '一' <= c <= '鿿']) > len(text) * 0.3:
        return text

    # 只用 mymemory（有超时控制），跳过 Google（无超时，容易卡死）
    try:
        result = _try_translate(text, "mymemory")
        if result and result != text:
            return result
    except Exception:
        pass
    return text


def _try_translate(text: str, backend: str) -> Optional[str]:
    """调用免费翻译 API（直接用 requests，不经过带重试的 http_client）"""
    if backend == "mymemory":
        try:
            import requests
            resp = requests.get(
                MYMEMORY_URL,
                params={"q": text[:500], "langpair": "en|zh-CN"},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("responseData", {}).get("translatedText", "")
                if result and result != text:
                    return result
        except Exception:
            pass

    return None


def _has_en_char(text: str) -> bool:
    """检查文本是否含英文字母"""
    return bool(re.search(r'[a-zA-Z]{4,}', text))


def _format_bbox(roi: Dict[str, Any]) -> str:
    b = roi['bbox']
    return (
        f"西: {b['west']:.4f}°E  "
        f"东: {b['east']:.4f}°E  "
        f"南: {b['south']:.4f}°N  "
        f"北: {b['north']:.4f}°N"
    )


def _format_links(links: list) -> str:
    if not links:
        return "_(暂无)_\n"
    lines = []
    for i, link in enumerate(links, 1):
        lines.append(f"{i}. [{link['label']}]({link['url']}) — {link.get('note', '')}")
    return "\n".join(lines)


def generate_report(
    roi: Dict[str, Any],
    mineral: str,
    mineral_info: Dict[str, Any],
    location: Dict[str, Any],
    geological: Dict[str, Any],
    geophysical: Dict[str, Any],
    geochemical: Dict[str, Any],
    remote_sensing: Dict[str, Any],
    live_data: Optional[Dict] = None,
    output_dir: Optional[Path] = None,
) -> str:
    """生成 ROI 针对性 Markdown 报告"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    from .logger import get_logger
    _rpt_log = get_logger("report")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    tu = location.get('center_tectonic')
    pb = location.get('petroleum_basin')
    is_oil = mineral in ('石油', '天然气', '油气')

    # ============================================================
    report = f"""# 🏔️ 矿产勘查前期资料收集报告

> **生成时间**: {now} | **目标矿种**: {mineral} | **图幅号**: {geological.get('map_sheet', 'N/A')}

---

## 一、ROI 位置

| 项目 | 内容 |
|------|------|
| **中心坐标** | {roi['center']['lon']:.4f}°E, {roi['center']['lat']:.4f}°N |
| **面积** | {roi['area_km2']:.2f} km² |
| **范围** | {_format_bbox(roi)} |
"""

    # --- 构造归属 ---
    if tu:
        report += f"""| **构造单元** | {tu['name']} ({tu.get('name_en', '')}) |
| **构造特征** | {tu.get('features', 'N/A')} |
| **区内主要矿产** | {', '.join(tu.get('major_minerals', []))} |
"""
    else:
        report += """| **构造单元** | 未识别（可能在海域或境外） |
"""

    # --- 跨单元 ---
    intersecting = location.get('intersecting_tectonics', [])
    if intersecting:
        report += f"""|
| **跨构造单元** | ROI 跨越以下构造单元: {', '.join(f"{i['name']}({i['overlap_fraction']*100:.0f}%)" for i in intersecting)} |
"""

    # --- 含油气盆地 ---
    if pb:
        report += f"""| **含油气盆地** | {pb['name']}（{pb['area_km2']:,} km²） |
| **主要成藏组合** | {', '.join(pb['main_plays'])} |
| **最大钻井深度** | {pb['max_well_depth']} m |
"""
    elif is_oil and not pb:
        report += """| **含油气盆地** | ⚠️ ROI 不在已知主要含油气盆地范围内 |
"""

    # --- 矿种在该单元的潜力 ---
    if tu and mineral not in ('石油', '天然气', '油气'):
        major = tu.get('major_minerals', [])
        element_to_chinese = {
            'Cu': '铜', 'Au': '金', 'Ag': '银', 'Fe': '铁', 'Pb': '铅', 'Zn': '锌',
            'W': '钨', 'Sn': '锡', 'Mo': '钼', 'Li': '锂', 'Co': '钴', 'Ni': '镍',
            'Sb': '锑', 'Hg': '汞', 'Al': '铝', 'U': '铀', 'Cr': '铬', 'Mn': '锰',
            'REE': '稀土', 'P': '磷', 'Oil': '石油', 'Gas': '天然气', 'Coal': '煤',
        }
        major_cn = {element_to_chinese.get(m, m) for m in major}
        mineral_match = [m for m in major_cn if mineral in m or m in mineral]
        if mineral_match:
            report += f"""|
| **矿种匹配** | ✅ '{mineral}' 在 {tu['name']} 已知矿产目录中 ({', '.join(mineral_match)}) |
"""
        else:
            report += f"""|
| **矿种匹配** | ⚠️ '{mineral}' 不在 {tu['name']} 主要矿产目录中，需结合具体成矿条件评估 |
"""

    report += "\n---\n\n## 二、该区域元素地球化学背景\n\n"

    # --- 化探背景值（构造单元特定 vs 全国对比） ---
    bgs = geochemical.get('backgrounds', {})
    thresholds = bgs.get('anomaly_thresholds', {})
    source_unit = bgs.get('source_unit', '全国')
    national_ref = bgs.get('national_reference', {})

    if thresholds:
        report += f"""**背景值来源**: {source_unit}（史长义等, 2016）

> 下表给出 **{source_unit}** 的 39 种元素水系沉积物背景值及异常分级。这些数值是你判断"某个化探高值是否构成异常"的定量依据——而非全国平均值。

| 元素 | {source_unit}背景值 | 全国背景值 | 弱异常(1.5×) | 中异常(2×) | 强异常(3×) |
|------|:---:|:---:|:---:|:---:|:---:|
"""
        for elem, vals in sorted(thresholds.items()):
            nat = national_ref.get(elem, '—')
            report += (
                f"| {elem} | {vals['background']} | {nat} | "
                f"{vals['weak_anomaly']} | "
                f"{vals['moderate_anomaly']} | "
                f"{vals['strong_anomaly']} |\n"
            )
        report += "\n"

    # --- 油气专属：六大要素 + 盆地匹配 ---
    if is_oil:
        report += "### 油气成藏关键要素（通用框架）\n\n"
        for se in mineral_info.get('six_elements', []):
            report += f"- **{se['element']}**: {se['description']}（关键参数: {se['key_params']}）\n"

        if pb:
            report += f"\n### {pb['name']} — 该盆地已知成藏特征\n\n"
            report += f"- **面积**: {pb['area_km2']:,} km²\n"
            report += f"- **主要成藏组合**: {', '.join(pb['main_plays'])}\n"
            report += f"- **最深钻井**: {pb['max_well_depth']} m\n"
            report += f"- **建议检索**: 在 CNKI/万方 检索 '{pb['name']} {mineral} 成藏'\n"
        report += "\n"

    report += "---\n\n## 三、地球物理数据\n\n"

    # --- 磁法 ---
    mag = geophysical.get('magnetic')
    if mag:
        report += f"""### 磁异常数据 ✅ 已获取

| 项目 | 内容 |
|------|------|
| **来源** | {mag['source']} |
| **分辨率** | {mag.get('resolution', 'N/A')} |
| **文件** | `{mag['file']}` |
| **说明** | 已按 ROI 外扩范围裁剪，可在 QGIS 中与地质图/化探叠合 |

"""
        # --- 嵌入磁异常分布图 ---
        if mag.get('map'):
            try:
                map_rel = Path(mag['map']).relative_to(output_dir).as_posix()
                report += f"![磁异常分布图]({map_rel})\n\n"
                report += (
                    "*图：ROI 范围内磁异常空间分布（nT），"
                    "星标为中心点，黑线为 ROI 边界*\n\n"
                )
            except ValueError:
                pass
    else:
        report += "### 磁异常数据 🔗 链接模式\n\n"
        for link in geophysical.get('links', []):
            if '磁' in link.get('label', ''):
                report += f"- [{link['label']}]({link['url']}) — {link.get('note', '')}\n"
        report += "\n"

    # --- 重力 ---
    grav = geophysical.get('gravity')
    if grav:
        report += f"""### 重力数据 ✅ 已获取

| 项目 | 内容 |
|------|------|
| **来源** | {grav['source']} |
| **分辨率** | {grav.get('resolution', 'N/A')} |
| **文件** | `{grav['file']}` |

"""
    else:
        report += "### 重力数据 🔗 链接模式\n\n"
        for link in geophysical.get('links', []):
            if '重力' in link.get('label', ''):
                report += f"- [{link['label']}]({link['url']}) — {link.get('note', '')}\n"
        report += "\n"

    # --- ICGEM ---
    icgem = geophysical.get('icgem')
    if icgem:
        report += f"""### ICGEM 重力场模型计算结果 ✅

| 项目 | 内容 |
|------|------|
| **来源** | {icgem['source']} |
| **模型** | {icgem.get('model', 'N/A')} |
| **截断阶次** | N = {icgem.get('max_degree', 'N/A')} |
| **分辨率** | {icgem.get('resolution', 'N/A')} |

"""
        for func_name, func_data in icgem.get("functionals", {}).items():
            display = "重力扰动" if func_name == "gravity_disturbance" else "大地水准面高"
            unit = func_data.get("unit", "")
            report += f"**{display}** ({unit})\n\n"
            report += f"| 统计量 | 值 |\n|--------|----|\n"
            report += f"| 最小值 | {func_data.get('min', 'N/A')} {unit} |\n"
            report += f"| 最大值 | {func_data.get('max', 'N/A')} {unit} |\n"
            report += f"| 平均值 | {func_data.get('mean', 'N/A')} {unit} |\n\n"
            if func_data.get('map'):
                try:
                    map_rel = Path(func_data["map"]).relative_to(output_dir).as_posix()
                    report += f"![{display}分布图]({map_rel})\n\n"
                except (ValueError, TypeError):
                    report += f"- 分布图: `{func_data['map']}`\n\n"
    elif geophysical.get('icgem_link'):
        report += f"### 在线重力场精细计算\n\n[ICGEM 在线计算]({geophysical['icgem_link']}) — 可自定义重力场模型和计算参数\n\n"
    else:
        report += "### ICGEM 重力场\n\nICGEM 在线计算链接已包含在上方链接列表中。\n\n"

    # --- DEM ---
    dem = geophysical.get('dem', {})
    report += "### DEM 地形数据\n\n"
    for key, info in dem.items():
        src = info.get('source', key)
        gs = info.get('gscloud_url', '')
        report += f"- **{src}**: [地理空间数据云]({gs})（国内高速）\n"

    tu_name = tu['name'] if tu else ''
    pb_name = pb['name'] if pb else ''

    # --- 实时查询论文 ---
    if live_data:
        papers = live_data.get("papers", [])
        if papers:
            _rpt_log.info("开始生成论文部分: %d 篇论文", len(papers))
            report += f"\n---\n\n## 四、区域已发表研究论文\n\n"
            report += f"> 自动检索 OpenAlex + Semantic Scholar，针对 **{tu_name}** + **{mineral}**\n\n"
            for i, p in enumerate(papers[:15], 1):
                authors = ", ".join(p.get("authors", [])[:3])
                cited = p.get("citation_count") or p.get("cited_by") or 0

                title = p.get('title', '')
                ab = p.get("abstract", "")

                # 翻译英文标题和摘要
                title_cn = ""
                if _has_en_char(title):
                    _rpt_log.debug("翻译论文 %d 标题...", i)
                    title_cn = _translate_en_to_cn(title)
                ab_cn = ""
                if _has_en_char(ab):
                    _rpt_log.debug("翻译论文 %d 摘要...", i)
                    ab_cn = _translate_en_to_cn(ab)
                _rpt_log.debug("论文 %d/%d 完成", i, min(len(papers), 15))

                report += f"{i}. **[{p.get('year','?')}] {title}**\n"
                if title_cn and title_cn != title:
                    report += f"   *{title_cn}*\n"
                report += f"   *{authors}* | 引用 {cited}\n"
                if ab_cn and ab_cn != ab:
                    report += f"   > {ab_cn[:250]}\n"
                elif ab:
                    report += f"   > {ab[:250]}\n"
                report += "\n"

        # --- ROI 中心物探值 ---
        rv = live_data.get("raster_values", {})
        if rv.get("magnetic_nt") is not None or rv.get("bouguer_mgal") is not None:
            report += "### ROI 中心点地球物理参数\n\n| 参数 | 数值 | 来源 |\n|------|------|------|\n"
            if rv.get("magnetic_nt") is not None:
                report += f"| 磁异常 | **{rv['magnetic_nt']} nT** | EMAG2 v3 (上延 4km) |\n"
            if rv.get("bouguer_mgal") is not None:
                report += f"| 布格重力异常 | **{rv['bouguer_mgal']} mGal** | WGM2012 |\n"
            report += "\n"

    report += "\n---\n\n## 五、地质资料在线检索\n\n"

    report += f"""以下链接已自动带入你的 ROI 坐标和图幅号：

### NGAC 全国地质资料馆

{_format_links(geological.get('ngac_geology', []))}

### 矿产地与钻孔

{_format_links(geological.get('ngac_mineral', []))}

### 化探异常图

{_format_links(geological.get('ngac_geochem', []))}

### 学术文献（按构造单元/盆地精准检索）

{_format_links(geological.get('cnki', []))}

### OneGeology 全球地质图

[在 OneGeology 查看 ROI]({geological.get('onegeology', '')})

---

## 六、遥感数据

"""

    s2_items = remote_sensing.get('sentinel2', [])
    if s2_items:
        report += f"**Sentinel-2 影像**：检索到 {len(s2_items)} 景（云量<10%）\n\n"
    else:
        report += "**Sentinel-2**: 需手动检索（见下方链接）\n\n"

    report += f"""### 影像检索

{_format_links(remote_sensing.get('earth_explorer_links', []))}

{_format_links(remote_sensing.get('gscloud_links', []))}

### ASTER 蚀变矿物填图参考

```{remote_sensing.get('aster_info', '')[:500]}...
```

---

## 七、数据收集优先级（基于 {tu_name if tu else '通用'} 特征）

"""

    for item in mineral_info.get('recommended_data_priority', []):
        report += f"{item['rank']}. **{item['data']}** → {item['method']}\n"

    report += f"""

---

## 八、下一步工作建议

1. **叠合分析**: 在 QGIS 中将磁法/重力/遥感与地质图叠合，关注 {tu_name + ' 的' if tu else ''}有利构造部位
2. **化探异常验证**: 对比上表 {source_unit}背景值，在 NGAC 化探图中圈出高于中异常(2×)阈值的区域
3. **文献深挖**: 逐一阅读上方 CNKI 链接中的前人研究，重点关注已报道的矿化点和异常查证结论
4. **实地踏勘**: 将"重磁异常 + 化探异常 + 有利地层/构造"三重叠合区列为优先验证靶区
5. **大比例尺数据**: 通过 NGAC 线下渠道获取 1:5万 地质图和化探原始点数据

---

> 📌 本报告由 Prospector 自动生成 | ROI: {roi['center']['lon']:.4f}°E, {roi['center']['lat']:.4f}°N | {tu_name if tu else ''}
"""

    _rpt_log.info("报告内容生成完毕, 开始写入文件...")
    report_path = output_dir / "00_项目摘要.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    _rpt_log.info("报告已保存: %s", report_path)
    return str(report_path)


def save_json_summary(
    roi: Dict[str, Any],
    mineral: str,
    mineral_info: Dict[str, Any],
    geological: Dict[str, Any],
    geophysical: Dict[str, Any],
    geochemical: Dict[str, Any],
    remote_sensing: Dict[str, Any],
    output_dir: Path,
    location: Optional[Dict] = None,
) -> str:
    """保存 JSON 格式摘要"""
    output_dir = Path(output_dir)

    summary = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "mineral": mineral,
            "roi_file": roi.get('filename', ''),
            "roi_area_km2": roi.get('area_km2'),
            "roi_center": roi['center'],
            "roi_bbox": roi['bbox'],
        },
        "location": {
            "tectonic_unit": location.get('center_tectonic', {}).get('name') if location else None,
            "petroleum_basin": location.get('petroleum_basin', {}).get('name') if location else None,
            "intersecting_units": [i['name'] for i in location.get('intersecting_tectonics', [])] if location else [],
        },
        "geophysical": {
            "magnetic_downloaded": geophysical.get('magnetic') is not None,
            "gravity_downloaded": geophysical.get('gravity') is not None,
        },
        "geochemical": {
            "background_unit": geochemical.get('backgrounds', {}).get('source_unit', '全国'),
            "element_count": len(geochemical.get('backgrounds', {}).get('anomaly_thresholds', {})),
        },
        "links": {
            "ngac_geology": len(geological.get('ngac_geology', [])),
            "ngac_mineral": len(geological.get('ngac_mineral', [])),
            "ngac_geochem": len(geological.get('ngac_geochem', [])),
            "cnki": len(geological.get('cnki', [])),
        },
        "remote_sensing": {
            "sentinel2_images": len(remote_sensing.get('sentinel2', [])),
        },
    }

    json_path = output_dir / "summary.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return str(json_path)
