"""MCPの次は何？ MCP AppsとWebMCPを体験する — PowerPoint生成スクリプト"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pathlib import Path

SHOTS = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT = Path(__file__).resolve().parent / "mcp-next.pptx"

BG = RGBColor(255, 255, 255)
CYAN = RGBColor(0x00, 0x77, 0x8F)
WHITE = RGBColor(0, 0, 0)  # 本文色（黒）
GRAY = RGBColor(0x5A, 0x66, 0x70)
PANEL = RGBColor(0xF2, 0xF5, 0xF7)
LINE = RGBColor(0xC5, 0xCE, 0xD4)
FONT = "Yu Gothic"
MONO = "Consolas"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
W = 13.333


def new_slide(notes=""):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def tb(s, x, y, w, h, text="", size=24, color=WHITE, bold=False, align=PP_ALIGN.LEFT,
       font=FONT, anchor=MSO_ANCHOR.TOP):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.name = Pt(size), bold, font
    f.color.rgb = color
    return box


def rich(s, x, y, w, h, paras, size=24, gap=10, anchor=MSO_ANCHOR.TOP):
    """paras: list of list of (text, style) ; style in {'', 'em', 'gray'}"""
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, runs in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        for text, st in runs:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.name = FONT
            r.font.bold = st == "em"
            r.font.color.rgb = CYAN if st == "em" else (GRAY if st == "gray" else WHITE)
    return box


def heading(s, text):
    tb(s, 0.7, 0.45, W - 1.4, 0.9, text, size=36, color=CYAN, bold=True)


def panel(s, x, y, w, h, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = line
    sh.line.width = Pt(1.25)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = 0.08
    sh.shadow.inherit = False
    return sh


def label_box(s, x, y, w, h, text, size=20, fill=PANEL, line=CYAN, color=WHITE, bold=False):
    sh = panel(s, x, y, w, h, fill=fill, line=line)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    lines = text.split("\n")
    for i, t in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = t
        r.font.size = Pt(size if i == 0 else size - 4)
        r.font.name = FONT
        r.font.bold = bold or i == 0
        r.font.color.rgb = color if i == 0 else GRAY
    return sh


def code_box(s, x, y, w, h, code, size=18):
    sh = panel(s, x, y, w, h, fill=RGBColor(0xF2, 0xF5, 0xF7), line=LINE)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_top = Inches(0.25)
    for i, line in enumerate(code.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = line if line else " "
        r.font.size = Pt(size)
        r.font.name = MONO
        r.font.color.rgb = RGBColor(0x1B, 0x25, 0x30)
    return sh


def arrow(s, x1, y1, x2, y2, both=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = CYAN
    c.line.width = Pt(2.5)
    ln = c.line._get_or_add_ln()
    from lxml import etree
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    tail = etree.SubElement(ln, f"{{{ns}}}tailEnd")
    tail.set("type", "triangle")
    if both:
        head = etree.SubElement(ln, f"{{{ns}}}headEnd")
        head.set("type", "triangle")
    return c


def divider(s, text, notes=""):
    s = new_slide(notes)
    tb(s, 0.8, 0, W - 1.6, 7.5, text, size=44, color=WHITE, bold=True,
       align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return s


def picture_fit(s, path, x, y, w, h):
    from PIL import Image
    iw, ih = Image.open(path).size
    r = min(w / iw, h / ih)
    pw, ph = iw * r, ih * r
    s.shapes.add_picture(str(path), Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2),
                         Inches(pw), Inches(ph))


def table(s, rows, x, y, w, col0, row_h=0.8, size=20, h=None):
    shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                             Inches(h or row_h * len(rows)))
    t = shp.table
    t.columns[0].width = Inches(col0)
    n = len(rows[0]) - 1
    for c in range(1, n + 1):
        t.columns[c].width = Inches((w - col0) / n)
    tblPr = shp._element.graphic.graphicData.tbl.tblPr
    tblPr.set("firstRow", "0")
    tblPr.set("bandRow", "0")
    for el in tblPr.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId"):
        tblPr.remove(el)
    for ri, row in enumerate(rows):
        t.rows[ri].height = Inches(row_h)
        for ci, val in enumerate(row):
            cell = t.cell(ri, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = HEAD if ri == 0 else PANEL
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.12)
            p = cell.text_frame.paragraphs[0]
            cell.text_frame.word_wrap = True
            p.alignment = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = val
            r.font.size = Pt(size)
            r.font.name = FONT
            r.font.bold = ri == 0 or ci == 0
            r.font.color.rgb = CYAN if (ri == 0 or ci == 0) else WHITE
    return shp


HEAD = RGBColor(0xE0, 0xF4, 0xF8)
HERE = Path(__file__).resolve().parent

# ================================================================ 本編
# 1 表紙
s = new_slide("表紙。持ち時間15分（デモ約5分を含む）。")
tb(s, 0.9, 2.0, W - 1.8, 2.4, "MCPの次は何？\nMCP AppsとWebMCPを体験する", size=48,
   color=CYAN, bold=True, anchor=MSO_ANCHOR.MIDDLE)
tb(s, 0.9, 5.0, W - 1.8, 0.6, "（イベント名・日付・名前は差し替え）", size=20, color=GRAY)

# 2 自己紹介
s = new_slide("自己紹介。文言は話し手が書く。")
heading(s, "自己紹介")
rich(s, 0.9, 1.9, W - 1.8, 4, [[("（ここに自己紹介を書く）", "gray")]], size=28)

# 3 問いかけ
s = new_slide("手を挙げてもらう。【約20秒】")
tb(s, 0.8, 0, W - 1.6, 7.5, "MCP、使ってますか？", size=54, bold=True,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# 4 MCPとは（文）
s = new_slide("【約40秒】技術仕様は深掘りしない。デモが動く前提だけ伝える。")
heading(s, "AIと外部システムをつなぐ共通規格「MCP」")
rich(s, 0.8, 1.8, W - 1.6, 4.8, [
    [("LLMは単体では、外部サービスの情報取得も操作もできない", "")],
    [("MCP", "em"), ("は、AIアプリケーションと外部ツールをつなぐ標準プロトコル", "")],
    [("MCP Host / Client / Server の役割に分かれる", "")],
    [("基本機能は Tools・Resources・Prompts の3つ", "")],
], size=28, gap=18)

# 5 MCPとは（図）
s = new_slide("【約30秒】Host=AIアプリ、Client=Hostの中の接続担当、Server=外部システム側。")
heading(s, "Host / Client / Server")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "AIアプリの中のクライアントが、外部のサーバーにつなぎます。", size=22)
label_box(s, 0.8, 2.2, 3.6, 1.6, "MCP Host\nAIアプリ（ChatGPTなど）", size=24)
label_box(s, 4.9, 2.2, 3.3, 1.6, "MCP Client\nHostの中の接続担当", size=24)
label_box(s, 9.0, 2.2, 3.6, 1.6, "MCP Server\n外部システム側", size=24, fill=HEAD)
arrow(s, 4.4, 3.0, 4.9, 3.0, both=True)
arrow(s, 8.2, 3.0, 9.0, 3.0, both=True)
tb(s, 0.8, 4.2, W - 1.6, 0.5, "サーバーが提供する3つの基本機能", size=18, color=GRAY, align=PP_ALIGN.CENTER)
for i, (n, d) in enumerate([("Tools", "操作する関数"), ("Resources", "読めるデータ"), ("Prompts", "定型の指示")]):
    label_box(s, 0.8 + i * 4.1, 4.8, 3.8, 1.5, f"{n}\n{d}", size=26)

# 6 接続設定
s = new_slide("【約20秒】stapy商店のMCPサーバーへの接続設定の例。")
heading(s, "接続設定の例")
tb(s, 0.9, 1.45, W - 1.8, 0.5, "stapy商店のMCPサーバーに、HTTPで接続します。", size=22)
code_box(s, 0.9, 2.1, 9.0, 3.8, '''{
  "mcpServers": {
    "stapy-shop": {
      "type": "http",
      "url": "https://stapy.studiooverdrive.com/mcp"
    }
  }
}''', size=24)

# 7 結果JSON
s = new_slide("【約30秒】人間・モデル向けの text と、プログラム・UI向けの structuredContent の2系統で返る。")
heading(s, "商品検索の結果例")
tb(s, 0.9, 1.4, W - 1.8, 0.5, "テキストと構造化データの両方が返ってきます。", size=22)
code_box(s, 0.9, 1.95, 11.5, 5.2, '''{ "jsonrpc": "2.0", "id": 3,
  "result": {
    "content": [{"type": "text",
      "text": "検索結果 1件:\\n- LT専用5分タイマー（lt-timer）¥2300 在庫24"}],
    "structuredContent": {
      "count": 1,
      "products": [{
        "id": "lt-timer", "name": "LT専用5分タイマー", "price": 2300,
        "category": "デスク周り", "tag": "おすすめ", "stock": 24,
        "image": "/images/lt-timer.webp",
        "desc": "Lightning Talk（LT）に最適。ボタン一つで5分の時間管理。",
        "features": ["ワンタッチで5分設定", "…"],
        "specs": [["商品名","LT専用5分タイマー"], ["サイズ","約 W60 × D60 × H58 mm"], "…"]
      }]
    },
    "isError": false } }''', size=15)

# 8 デモ
s = new_slide(
    "【デモ 約5分】直前に「デモリセット」でカートを空にする。\n"
    "期待結果（4方式共通）：LT専用5分タイマー ¥2,300 + ステッカーセット ¥400 = ¥2,700\n"
    "① 手で操作（約1分）：stapy.studiooverdrive.com で検索 → 価格3,000円 → 2点をカートへ\n"
    "② MCP（約1分）：ChatGPT（Webブラウザ）にstapy商店のMCPをつなぎ、同じ依頼を日本語で\n"
    "③ MCP Apps（約1.5分）：ChatGPTで「ショップを開いて」→ チャット内UIからカートへ\n"
    "④ WebMCP（約1.5分）：WebMCP対応環境でstapy商店を開き、同じ依頼 → 画面のカートパネルが開く")
heading(s, "デモ：同じ依頼を4つの方法で")
panel(s, 0.8, 1.6, W - 1.6, 1.5, fill=HEAD, line=CYAN)
tb(s, 1.1, 1.6, W - 2.2, 1.5, "LTに登壇する人に、予算3,000円以内でプレゼントを探してカートに入れて",
   size=26, bold=True, anchor=MSO_ANCHOR.MIDDLE)
for i, (n, d) in enumerate([("① 手で操作", "Webサイト"), ("② MCP", "チャット"),
                            ("③ MCP Apps", "チャット内UI"), ("④ WebMCP", "ブラウザ")]):
    label_box(s, 0.8 + i * 3.0, 3.7, 2.75, 1.7, f"{n}\n{d}", size=24)
tb(s, 0.8, 5.9, W - 1.6, 0.6, "stapy.studiooverdrive.com", size=22, color=GRAY, align=PP_ALIGN.CENTER)

# 9 中扉
divider(s, "なんで動いたの？", "【8秒】ここから、デモが動いた理由を説明する。技術仕様は深掘りしない。")

# 10 stapy商店のTools
s = new_slide(
    "【約40秒】商品検索・カート操作をToolsとして公開している。\n"
    "MCPのツールはモデル向け10個＋MCP Apps UI専用(ui_*)8個の18個。WebMCPはページのwebmcp.jsが8個登録。\n"
    "3方式とも同じサービス層・同じカートにつながるので、同じ¥2,700になる。")
heading(s, "stapy商店は操作をToolsとして公開")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "商品検索とカート操作を、AIが呼べるツールにしています。", size=22)
code_box(s, 0.8, 2.1, 5.8, 4.4, '''search_products
get_product
add_to_cart
update_cart
remove_from_cart
get_cart
preview_order
confirm_order''', size=22)
rich(s, 7.0, 2.2, 5.6, 4.2, [
    [("MCP", "em"), ("　サーバーのツールとして", "")],
    [("MCP Apps", "em"), ("　UIからも同じ操作", "")],
    [("WebMCP", "em"), ("　ページが同じ名前で登録", "")],
], size=24, gap=22)

# 11 歴史
s = new_slide(
    "【約45秒】\n2024-11：AnthropicがMCPをオープンな標準として発表。\n"
    "2025年：MCP-UIやOpenAI Apps SDKなど、チャット内にUIを表示する仕組みが登場。\n"
    "2026-01-26：MCP AppsがMCPの最初の公式拡張として公開。\n"
    "2026-07-28：拡張の枠組みを含む版。ステートレス化（セッションID廃止）も同じ版。\n"
    "2027-03-30：次の版（予定）。以降は3月と9月に年2回。\n"
    "出典：anthropic.com、blog.modelcontextprotocol.io")
heading(s, "MCPはツール接続から、対話できるUIへ")
events = [
    ("2024-11", "MCP公開\nAnthropicが発表"),
    ("2025", "UI対応の試み\nMCP-UI・OpenAI Apps SDK"),
    ("2026-01", "MCP Apps\n公式拡張に"),
    ("2026-07-28", "拡張の枠組みを\n含む版"),
    ("2027-03-30", "次の版\n（予定）"),
]
y_line = 3.4
ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1.0), Inches(y_line), Inches(12.3), Inches(y_line))
ln.line.color.rgb = LINE
ln.line.width = Pt(3)
for i, (d, t) in enumerate(events):
    cx = 1.9 + i * 2.38
    last = i == len(events) - 1
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 0.15), Inches(y_line - 0.15), Inches(0.3), Inches(0.3))
    dot.fill.solid()
    dot.fill.fore_color.rgb = BG if last else CYAN
    dot.line.color.rgb = CYAN
    dot.line.width = Pt(2.5)
    tb(s, cx - 1.15, 2.4, 2.3, 0.5, d, size=20, color=CYAN, bold=True, align=PP_ALIGN.CENTER)
    tb(s, cx - 1.18, 3.8, 2.36, 1.6, t, size=18, align=PP_ALIGN.CENTER, color=GRAY if last else WHITE)
tb(s, 0.8, 6.5, W - 1.6, 0.5, "出典：anthropic.com、blog.modelcontextprotocol.io", size=14, color=GRAY)

# 12 MCP Apps
s = new_slide("【約50秒】stapy商店は ui://stapy/shop.html を公開。UIのボタンは裏で ui_* ツールを呼ぶ。")
heading(s, "チャットの中に、UIが出る！")
rich(s, 0.8, 1.7, 6.0, 4.8, [
    [("従来のMCP", "gray")],
    [("主にテキストや構造化データを返す", "")],
    [("MCP Apps", "em")],
    [("商品一覧・フォーム・グラフなどのUIを表示できる", "")],
    [("MCPサーバーがUIリソースを提供し、AIアプリが埋め込んで表示する", "")],
], size=24, gap=10)
picture_fit(s, HERE / "img" / "shop_ui_crop.png", 7.2, 1.4, 5.4, 5.8)

# 13 WebMCP
s = new_slide(
    "【約45秒】ページ自身がツールを登録する。サーバーは不要で、ページのJavaScriptが実行する。\n"
    "Toolsのみで、ResourcesとPromptsはない。")
heading(s, "Webサイト自身がAIに操作機能を公開する")
rich(s, 0.8, 1.7, W - 1.6, 4.9, [
    [("WebMCP", "em"), ("は、Google・Microsoftが中心となって推進するブラウザ向けのWeb標準提案", "")],
    [("MCPやMCP Appsとは別系統の仕様", "")],
    [("Webサイトがブラウザ上でツールを登録する", "")],
    [("AIは画面上のボタンを推測してクリックする代わりに、構造化されたツールを呼び出せる", "")],
], size=26, gap=16)

# 14 実装イメージ
s = new_slide(
    "【約40秒】API は2種類：HTMLフォームに属性を付ける宣言的API、JavaScriptの命令的API。\n"
    "stapy商店では webmcp.js が8個のツールを登録している。")
heading(s, "実装イメージ")
code_box(s, 0.8, 1.5, 7.6, 4.9, '''document.modelContext.registerTool({
  name: "search_products",
  description: "商品を検索する",
  inputSchema: {
    type: "object",
    properties: {
      query: { type: "string" }
    }
  },
  execute: async ({ query }) => {
    return await searchProducts(query);
  }
});''', size=19)
rich(s, 8.8, 1.6, 4.0, 4.9, [
    [("HTMLフォームの宣言的APIと、JavaScriptの命令的APIがある", "")],
    [("Chromeはオリジントライアル中、ChatGPT Desktopは対応済み", "")],
], size=20, gap=18)
tb(s, 0.8, 6.6, W - 1.6, 0.5, "※簡略化したサンプル。2026年11月時点では試験段階の機能です（developer.chrome.com）",
   size=14, color=GRAY)

# 15 3方式の表
s = new_slide("【約40秒】同じ操作でも、UIとツールをどこに置くかが違う。")
heading(s, "同じ操作でも、UIとツールの置き場所が違う")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "3方式を、つなぐ先と画面で比べます。", size=22)
table(s, [
    ("", "MCP", "MCP Apps", "WebMCP"),
    ("接続対象", "MCPサーバー", "MCPサーバー", "Webページ"),
    ("操作UI", "主にAIチャット", "チャット内UI", "Webサイト"),
    ("接続設定", "必要", "必要", "対応ブラウザ等が必要"),
    ("用途", "API・自動処理", "対話型アプリ", "ブラウザ操作"),
], 0.8, 2.15, W - 1.6, 2.4, row_h=0.9, size=22)

# 16 メリット・デメリット
s = new_slide("【約50秒】3つは単純な新旧関係ではなく、利用する場所と目的が異なる。")
heading(s, "メリット・デメリット")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "どれが新しいかではなく、使う場所で選びます。", size=22)
table(s, [
    ("", "メリット", "デメリット"),
    ("MCP", "既存APIや業務システムと連携しやすい", "クライアント側の接続設定が必要"),
    ("MCP Apps", "ユーザーが操作しやすいUIを提供できる", "対応するホストが必要"),
    ("WebMCP", "既存Webサイトの操作機能をAIに公開できる", "対応環境が限定的で、仕様も発展途上"),
], 0.8, 2.15, W - 1.6, 2.2, row_h=1.0, size=20)
tb(s, 0.8, 6.3, W - 1.6, 0.6, "3つは単純な新旧関係ではなく、利用する場所と目的が異なる", size=24, color=CYAN, bold=True)

# 17 MCPとWebMCPの違い
s = new_slide(
    "【約50秒】名前は似ているが別物。AnthropicはMCPを2025-12-09にAAIF（Linux Foundation傘下）へ寄贈。\n"
    "WebMCPはW3C Web Machine Learning Community Groupのドラフト仕様。")
heading(s, "MCPとWebMCPは別物")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "名前は似ていますが、主導する組織も仕様も別です。", size=22)
table(s, [
    ("", "MCP", "WebMCP"),
    ("発案・主導", "Anthropic", "Google・Microsoft"),
    ("標準化組織", "Linux Foundation傘下のAAIF", "W3C Web Machine Learning CG"),
    ("主な目的", "AIと外部システムの接続", "AIによるWebページ操作"),
    ("技術", "JSON-RPCなど", "JavaScript / HTML API"),
    ("仕様上の関係", "独立", "MCPに着想を得た独立仕様"),
], 0.8, 2.1, W - 1.6, 4.2, row_h=0.72, size=20)
tb(s, 0.8, 6.55, W - 1.6, 0.6,
   "※AIエージェントが操作するのは同じ。MCPはプロトコル経由、WebMCPはブラウザ内のページ経由",
   size=18, color=GRAY)

# 18 統合
s = new_slide(
    "【約40秒】2026-11-10 MCP Apps SDK v2.1.0 で WebMCPとの双方向連携が入った。\n"
    "既存のMCP通信プロトコルは変えず、SDK側で相互接続。既定で有効、webMcpBridge: false で無効化。\n"
    "stapy商店のSDKは v2.0.4 なので、今日のデモにはこの橋渡しは入っていない。\n"
    "出典：github.com/modelcontextprotocol/ext-apps/releases")
heading(s, "MCP AppsとWebMCPがつながった！")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "MCP Apps SDK v2.1.0（2026年11月10日）で、双方向に連携できるようになりました。",
   size=22)
label_box(s, 0.9, 2.5, 4.6, 1.6, "MCP Apps\nApp.registerTool()", size=26)
label_box(s, 7.8, 2.5, 4.6, 1.6, "WebMCP\ndocument.modelContext", size=26)
arrow(s, 5.5, 3.3, 7.8, 3.3, both=True)
tb(s, 5.4, 2.6, 2.5, 0.6, "SDKが橋渡し", size=20, color=CYAN, bold=True, align=PP_ALIGN.CENTER)
rich(s, 0.9, 4.6, W - 1.8, 2.2, [
    [("MCP Apps → WebMCP　登録したツールを document.modelContext にも公開", "")],
    [("WebMCP → MCP Apps　ページのツールを tools/list・tools/call から利用", "")],
    [("既存のMCP通信プロトコルは変えず、SDK側で相互接続（既定で有効）", "gray")],
], size=20, gap=10)

# 19 まとめ
s = new_slide("【約30秒】")
heading(s, "まとめ")
rich(s, 0.8, 1.8, W - 1.6, 5, [
    [("MCP", "em"), ("　AIと外部システムをつなぐ共通規格", "")],
    [("MCP Apps", "em"), ("　MCPサーバーが、チャットの中にUIを出す", "")],
    [("WebMCP", "em"), ("　Webページ自身が、ブラウザでAIにツールを公開する（MCPとは別の仕様）", "")],
    [("3つは新旧の関係ではなく、使う場所と目的が違う。SDK v2.1.0 でつながり始めている", "")],
], size=26, gap=22)

# ================================================================ おまけ
divider(s, "おまけ", "時間が余ったとき・質疑で聞かれたときだけ進む。")

# 21 Python実装
s = new_slide("ローカル版。4方式すべて同じサービス層・SQLiteカートを共有し、ビジネスロジックの重複実装はない。")
heading(s, "おまけ：Pythonでの実装")
table(s, [
    ("層", "技術"),
    ("言語", "Python 3.12（requires ≥3.11）"),
    ("Webフレームワーク", "FastAPI 0.162.7 + uvicorn 0.54.0"),
    ("MCP", "python-mcp SDK 2.3.0（Streamable HTTP /mcp + stdio、18ツール＋UIリソース）"),
    ("バリデーション", "pydantic 2.14.3"),
    ("DB", "SQLite（cart_items / op_log / orders、2段階注文）"),
    ("フロントエンド", "バニラ HTML/CSS/JS（ビルドなし）"),
    ("MCP Apps", "shop_app.html + ext-apps SDK、ui://stapy/shop.html"),
    ("WebMCP", "document.modelContext.registerTool / getTools / executeTool"),
], 0.8, 1.5, W - 1.6, 5.6, row_h=0.62, size=16, )
s.shapes[-1].table.columns[0].width = Inches(2.8)
s.shapes[-1].table.columns[1].width = Inches(W - 1.6 - 2.8)

# 22 Workers
s = new_slide("公開版（deploy/cloudflare ブランチ）。SDKがWorkers非対応のため、MCPのJSON-RPCは自前実装。ツール定義はPython正本から生成。")
heading(s, "おまけ：デプロイ版（Cloudflare Workers）")
table(s, [
    ("層", "技術"),
    ("ランタイム", "Cloudflare Workers（TypeScript 5.9、無料枠）"),
    ("DB", "Cloudflare D1（SQLite 互換、同一スキーマ＋mcp_sessions）"),
    ("静的配信", "Workers Static Assets"),
    ("MCP", "JSON-RPC を自前実装（ツール定義はPython正本から生成）"),
    ("コード生成", "worker/build.py → products.ts / tools.ts / uiHtml.ts"),
    ("ドメイン", "Worker Custom Domain stapy.studiooverdrive.com"),
    ("ツールチェーン", "wrangler 4.162.0、@cloudflare/workers-types 5系、Node 24.13"),
], 0.8, 1.5, W - 1.6, 5.2, row_h=0.65, size=16)
s.shapes[-1].table.columns[0].width = Inches(2.8)
s.shapes[-1].table.columns[1].width = Inches(W - 1.6 - 2.8)

# 23 WebMCPの最新動向
s = new_slide("出典：webmachinelearning.github.io/webmcp、github.com/webmachinelearning/webmcp の implementation-status.md")
heading(s, "おまけ：WebMCPの最新動向")
rich(s, 0.8, 1.7, W - 1.6, 5, [
    [("11月9日", "em"), ("　仕様ドラフトが更新され、策定が継続中", "")],
    [("11月2日", "em"), ("　outputSchema が追加され、出力の構造もJSON Schemaで宣言できるように", "")],
    [("対応状況", "em"), ("　Chrome 149・Edge 150 はオリジントライアル、ChatGPT Desktop は対応済み", "")],
    [("予定", "em"), ("　Brave（Leo AI）は2027年1月、Meta Ray-Ban Display は近日対応", "")],
], size=24, gap=20)

# 24 リンク
s = new_slide("")
heading(s, "おまけ：リンク")
rich(s, 0.8, 1.7, W - 1.6, 5, [
    [("stapy商店（デモ）", "gray")],
    [("https://stapy.studiooverdrive.com/", "")],
    [("リポジトリ", "gray")],
    [("https://github.com/okajun35/stapy-shop-mcp-demo", "")],
    [("WebMCP 仕様", "gray")],
    [("https://webmachinelearning.github.io/webmcp", "")],
], size=24, gap=6)

prs.save(OUT)
print("saved", OUT, len(prs.slides._sldIdLst), "slides")
