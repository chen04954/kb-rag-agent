"""Generate resume PDF from desktop markdown (Chinese fonts on Windows)."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

DESKTOP = Path.home() / "Desktop"
MD_PATH = DESKTOP / "谢辉-简历-AI应用开发.md"
OUT_PATH = DESKTOP / "谢辉-简历-AI应用开发.pdf"

SECTION_HEADERS = {
    "教育经历",
    "实习经历",
    "专业技能",
    "项目经历",
    "资格证书",
    "内容：",
    "实习成果：",
}


def pick_font() -> Path:
    for candidate in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No Chinese font found under C:\\Windows\\Fonts")


def main() -> None:
    text = MD_PATH.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in text.splitlines()]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("cn", "", str(pick_font()))
    pdf.set_font("cn", size=10.5)

    width = pdf.w - pdf.l_margin - pdf.r_margin
    for line in lines:
        line = line.replace("\t", "    ")
        if not line.strip():
            pdf.ln(3)
            continue
        if line == "谢辉":
            pdf.set_font("cn", size=16)
            pdf.multi_cell(width, 8, line)
            pdf.set_font("cn", size=10.5)
            continue
        if line in SECTION_HEADERS or line.endswith("ai工程师"):
            pdf.ln(2)
            pdf.set_font("cn", size=11)
            pdf.multi_cell(width, 6, line)
            pdf.set_font("cn", size=10.5)
            continue
        pdf.multi_cell(width, 5.5, line)

    pdf.output(str(OUT_PATH))
    print(f"OK: {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
