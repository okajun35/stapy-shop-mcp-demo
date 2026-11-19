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


# ---------------------------------------------------------------- 1 表紙
s = new_slide("表紙。持ち時間15分（デモ約5分を含む）。")
tb(s, 0.9, 2.0, W - 1.8, 2.4, "MCPの次は何？\nMCP AppsとWebMCPを体験する", size=48,
   color=CYAN, bold=True, anchor=MSO_ANCHOR.MIDDLE)
tb(s, 0.9, 5.0, W - 1.8, 0.6, "（イベント名・日付・名前は差し替え）", size=20, color=GRAY)

# ---------------------------------------------------------------- 2 自己紹介
s = new_slide("自己紹介。文言は話し手が書く。")
heading(s, "自己紹介")
rich(s, 0.9, 1.9, W - 1.8, 4, [[("（ここに自己紹介を書く）", "gray")]], size=28)

# ---------------------------------------------------------------- 3 問い1
s = new_slide("手を挙げてもらう。【約20秒】")
tb(s, 0.8, 0, W - 1.6, 7.5, "MCP、使ってますか？", size=54, bold=True,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# ---------------------------------------------------------------- 4 問い2
s = new_slide("2つ目で手が減る。ここが本編の入口。【約20秒】")
tb(s, 0.8, 0, W - 1.6, 7.5, "じゃあ、作ってますか？", size=54, bold=True,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# ---------------------------------------------------------------- 5 stapy商店 + デモ①
s = new_slide(
    "【約40秒＋デモ① 約1分】\n"
    "架空のEC「stapy商店」。この後の4方式すべてで同じ依頼をする。\n"
    "依頼：LTに登壇する人に、予算3,000円以内でプレゼントを探してカートに入れる。\n"
    "期待結果：LT専用5分タイマー ¥2,300 + ステッカーセット ¥400 = ¥2,700。\n"
    "デモ①：手で検索（LT）→ 価格を3,000円に絞る → 2点をカートへ → 合計¥2,700。\n"
    "直前に「デモリセット」でカートを空にしておく。")
heading(s, "stapy商店")
picture_fit(s, SHOTS / "web_ui.png", 0.7, 1.5, 7.6, 5.4)
panel(s, 8.7, 1.8, 4.0, 3.6)
rich(s, 8.9, 1.95, 3.6, 3.4, [
    [("AIへの依頼", "gray")],
    [("LTに登壇する人に、予算3,000円以内でプレゼントを探してカートに入れて", "")],
], size=22)
tb(s, 8.7, 5.7, 4.0, 0.6, "まずは手で操作", size=22, color=CYAN, bold=True)

# ---------------------------------------------------------------- 6 中扉
divider(s, "これ、AIに任せられたら？",
        "【8秒】聴衆の心の声。次のスライドが答え。")

# ---------------------------------------------------------------- 7 MCPとは
s = new_slide(
    "【約40秒】\n"
    "LLMだけでは外部サービスの情報取得も操作もできない。\n"
    "MCPは、AIアプリと外部ツールをつなぐ共通の標準プロトコル。\n"
    "Host=AIアプリ、Client=接続を担当する部品、Server=外部システム側。\n"
    "Serverが公開するのは3種類。stapy商店は商品検索やカート操作をToolsとして出している。\n"
    "技術仕様は深掘りしない。最初のデモが動いた理由だけ伝える。")
heading(s, "AIと外部をつなぐ共通規格「MCP」")
label_box(s, 0.8, 1.9, 3.6, 1.7, "AIアプリ\nHost（ChatGPTなど）", size=24)
label_box(s, 4.9, 1.9, 3.3, 1.7, "MCPクライアント\nHostの中の接続担当", size=22)
label_box(s, 9.0, 1.9, 3.6, 1.7, "MCPサーバー\nstapy商店", size=24, fill=RGBColor(0xE0, 0xF4, 0xF8))
arrow(s, 4.4, 2.75, 4.9, 2.75, both=True)
arrow(s, 8.2, 2.75, 9.0, 2.75, both=True)
tb(s, 9.0, 3.7, 3.6, 0.5, "サーバーが公開するもの", size=18, color=GRAY, align=PP_ALIGN.CENTER)
for i, (n, d) in enumerate([("Tools", "操作する関数"), ("Resources", "読めるデータ"), ("Prompts", "定型の指示")]):
    label_box(s, 0.8 + i * 4.1, 4.5, 3.8, 1.6, f"{n}\n{d}", size=26)
tb(s, 0.8, 6.4, W - 1.6, 0.6, "stapy商店は、商品検索とカート操作をToolsとして公開", size=22)

# ---------------------------------------------------------------- 8 接続設定
s = new_slide(
    "【約25秒】\n接続設定はこの数行だけ。URLを1つ書く。\n"
    "ChatGPTなど各クライアントでは画面からURLを入れるだけのことが多い。")
heading(s, "接続はこの数行だけ")
code_box(s, 0.9, 1.7, 8.0, 3.6, '''{
  "mcpServers": {
    "stapy-shop": {
      "type": "http",
      "url": "https://stapy.studiooverdrive.com/mcp"
    }
  }
}''', size=22)
tb(s, 0.9, 5.7, W - 1.8, 0.6, "AI側が用意するのは、サーバーのURLだけ", size=24)

# ---------------------------------------------------------------- 9 結果JSON + デモ②
s = new_slide(
    "【約30秒＋デモ② 約1分】\n"
    "実際の search_products の応答を抜粋。人間向けのtextと、プログラム向けのstructuredContentの2系統で返る。\n"
    "デモ②：ChatGPTのWebブラウザにstapy商店のMCPを接続し、同じ依頼を日本語で投げる。\n"
    "AIがsearch_products → add_to_cart を呼び、合計¥2,700になることを見せる。\n"
    "（カートは人間の手操作と共有。画面を見せるなら /logs.html の MCP チャネル）")
heading(s, "返ってくるのは構造化データ")
tb(s, 0.9, 1.45, W - 1.8, 0.5, "search_products {q: \"LT\", max_price: 3000} の結果", size=20, color=GRAY)
code_box(s, 0.9, 2.0, 11.5, 4.9, '''{ "result": {
    "content": [{ "type": "text",
      "text": "検索結果 3件:\\n- ノートブック ¥800\\n- LT専用5分タイマー ¥2300 …" }],
    "structuredContent": {
      "count": 3,
      "products": [{ "id": "lt-timer", "name": "LT専用5分タイマー",
                     "price": 2300, "stock": 24, "…" }]
    },
    "isError": false } }''', size=20)

# ---------------------------------------------------------------- 10 中扉
divider(s, "でも、返ってくるのは文字だけ？",
        "【8秒】次は、UIが返ってくる話。")

# ---------------------------------------------------------------- 11 年表
s = new_slide(
    "【約45秒】\n"
    "2024-11 MCP公開（Anthropic）。\n"
    "2025-11 MCP-UIとOpenAI Apps SDKを土台に、MCP AppsがSEP-1865として提案された。\n"
    "2026-01-26 MCP Appsが最初の公式拡張として公開。Claude、ChatGPT、VS Code、Gooseなどが対応。\n"
    "2026-07-28 版：拡張の枠組みが仕様に入る。ステートレス化（セッションIDの廃止）も同じ版。\n"
    "2027-03-30：次の版の予定。以降は3月と9月の最終火曜日に年2回リリース。\n"
    "出典：modelcontextprotocol.io のブログとリリースノート。")
heading(s, "MCP公開からAppsまで")
events = [
    ("2024-11", "MCP公開"),
    ("2025-11", "Appsを提案"),
    ("2026-01-26", "MCP Apps\n公式拡張に"),
    ("2026-07-28", "拡張の枠組みが\n仕様に入る"),
    ("2027-03-30", "次の版（予定）"),
]
y_line = 3.6
ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1.0), Inches(y_line), Inches(12.3), Inches(y_line))
ln.line.color.rgb = LINE
ln.line.width = Pt(3)
for i, (d, t) in enumerate(events):
    cx = 1.9 + i * 2.38
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 0.15), Inches(y_line - 0.15), Inches(0.3), Inches(0.3))
    dot.fill.solid()
    last = i == len(events) - 1
    dot.fill.fore_color.rgb = BG if last else CYAN
    dot.line.color.rgb = CYAN
    dot.line.width = Pt(2.5)
    tb(s, cx - 1.1, 2.55, 2.2, 0.5, d, size=20, color=CYAN, bold=True, align=PP_ALIGN.CENTER)
    tb(s, cx - 1.15, 4.0, 2.3, 1.2, t, size=22, align=PP_ALIGN.CENTER,
       color=GRAY if last else WHITE)

# ---------------------------------------------------------------- 12 MCP Apps + デモ③
s = new_slide(
    "【約50秒＋デモ③ 約1.5分】\n"
    "従来のMCPは主にテキストと構造化データを返す。\n"
    "MCP Appsは、サーバーがUIリソース（ui://…）を提供し、AIアプリがiframeで埋め込んで表示する。\n"
    "stapy商店は ui://stapy/shop.html を公開している。\n"
    "デモ③：ChatGPTで「ショップを開いて」と頼み、チャット内の商品一覧UIからカートに入れる。\n"
    "UI内のボタンは裏でui_*ツールを呼んでいる。同じカートに入り、合計¥2,700になる。")
heading(s, "チャットの中に、UIが出る！")
rich(s, 0.8, 1.7, 5.2, 4.5, [
    [("従来のMCP", "gray")],
    [("テキストと構造化データを返す", "")],
    [("", "")],
    [("MCP Apps", "em")],
    [("商品一覧やフォームを表示し、その場で操作できる", "")],
], size=24, gap=6)
tb(s, 0.8, 5.3, 5.2, 0.6, "サーバーがUIを渡し、AIアプリが埋め込む", size=22, color=CYAN, bold=True)
picture_fit(s, Path(__file__).resolve().parent / "img" / "shop_ui_crop.png", 7.2, 1.4, 5.4, 5.8)

# ---------------------------------------------------------------- 13 中扉
divider(s, "Webサイト自身が、操作方法を教えてくれたら？",
        "【8秒】MCPサーバーを別に用意せず、ページ自身が公開する話。")

# ---------------------------------------------------------------- 14 WebMCP
s = new_slide(
    "【約45秒】\n"
    "WebMCPは、Webページがブラウザ上でツールを登録する仕組み。Google・Microsoftの提案で、W3Cのコミュニティグループで仕様策定中。\n"
    "AIは画面のボタンを推測してクリックする代わりに、構造化されたツールを呼べる。\n"
    "MCPに着想を得た別系統の仕様。サーバーは不要で、ページのJavaScriptが実行する。\n"
    "対応するのはToolsのみ。ResourcesとPromptsはない。\n"
    "APIは2種類：JavaScriptの命令的API、HTMLフォームに属性を付ける宣言的API。\n"
    "対応状況：Chromeはオリジントライアル（149）、Edgeも（150）。ChatGPT Desktopは対応済み。Brave（Leo）は2027年1月予定、Meta Ray-Ban Displayは近日対応。")
heading(s, "ボタンを推測せず、ツールを呼ぶ「WebMCP」")
rich(s, 0.8, 1.7, W - 1.6, 4.8, [
    [("ページ自身", "em"), ("が、ブラウザにツールを登録する", "")],
    [("AIは画面を推測せず、構造化されたツールを呼べる", "")],
    [("JavaScriptの命令的API ＋ HTMLフォームの宣言的API", "")],
    [("MCPとは別系統の仕様（W3Cで策定中）", "")],
], size=28, gap=16)

# ---------------------------------------------------------------- 15 コード + デモ④
s = new_slide(
    "【約30秒＋デモ④ 約1.5分】\n"
    "簡略化したコード。stapy商店ではウェブページ側のwebmcp.jsが8個のツールを登録している。\n"
    "2026年11月時点では試験段階の機能。\n"
    "デモ④：WebMCP対応環境でstapy商店を開き、同じ依頼をする。\n"
    "AIが登録済みツールを呼ぶと、カートパネルが開いて画面に反映される。MCPと違い、結果が画面に出る。\n"
    "その後、人間が同じ画面を続けて操作できる。")
heading(s, "実装イメージ")
code_box(s, 0.9, 1.6, 8.3, 4.9, '''document.modelContext.registerTool({
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
});''', size=20)
panel(s, 9.6, 1.9, 3.2, 2.2)
rich(s, 9.8, 2.05, 2.8, 2.0, [
    [("簡略化したサンプル", "")],
    [("2026年11月時点では試験段階の機能です", "gray")],
], size=20)

# ---------------------------------------------------------------- 16 使い分け
s = new_slide(
    "【約60秒】\n"
    "MCP：既存APIや業務システムと連携しやすい。クライアント側に接続設定が要る。\n"
    "MCP Apps：ユーザーが操作しやすいUIを出せる。対応するホストが要る。\n"
    "WebMCP：既存Webサイトの操作をAIに公開できる。対応環境が限られ、仕様も発展途上。\n"
    "3つは新旧の関係ではなく、使う場所と目的が違う。\n"
    "4方式すべてで同じ¥2,700に着地したことを一言添える（同じサービス層・同じカート）。")
heading(s, "3方式の使い分け")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "同じ商品検索とカート操作でも、AIとつなぐ場所が違います。", size=22)
rows = [
    ("", "MCP", "MCP Apps", "WebMCP"),
    ("つなぐ先", "MCPサーバー", "MCPサーバー", "Webページ"),
    ("操作する画面", "AIチャット（テキスト）", "チャット内のUI", "Webサイト"),
    ("向くこと", "API・自動処理", "対話型アプリ", "ブラウザ操作"),
]
tbl_shape = s.shapes.add_table(len(rows), 4, Inches(0.8), Inches(2.2), Inches(W - 1.6), Inches(3.6))
tbl = tbl_shape.table
tbl.columns[0].width = Inches(2.6)
for c in (1, 2, 3):
    tbl.columns[c].width = Inches((W - 1.6 - 2.6) / 3)
tblPr = tbl_shape._element.graphic.graphicData.tbl.tblPr
tblPr.set("firstRow", "0")
tblPr.set("bandRow", "0")
from lxml import etree
for el in tblPr.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId"):
    tblPr.remove(el)
for ri, row in enumerate(rows):
    tbl.rows[ri].height = Inches(0.9)
    for ci, val in enumerate(row):
        cell = tbl.cell(ri, ci)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xE0, 0xF4, 0xF8) if ri == 0 else PANEL
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
        r = p.add_run()
        r.text = val
        r.font.size = Pt(24)
        r.font.name = FONT
        r.font.bold = ri == 0 or ci == 0
        r.font.color.rgb = CYAN if (ri == 0 or ci == 0) else WHITE
tb(s, 0.8, 6.2, W - 1.6, 0.6, "新旧の関係ではなく、使う場所と目的が違う", size=24, color=CYAN, bold=True)

# ---------------------------------------------------------------- 17 つながり始めている
s = new_slide(
    "【約40秒】\n"
    "2026-11-10公開の MCP Apps SDK v2.1.0 で、WebMCPとの相互運用が入った。\n"
    "App.registerTool() で登録したツールは、document.modelContext にも公開される。\n"
    "逆に、ページが document.modelContext に登録したツールは、MCP Appsの tools/list・tools/call から使える。\n"
    "既存のMCP通信プロトコルは変えず、SDK側で橋渡ししている。既定で有効、webMcpBridge: false で無効化。\n"
    "注意：stapy商店が使っているSDKは v2.0.4 なので、このデモにはブリッジは入っていない。\n"
    "出典：github.com/modelcontextprotocol/ext-apps/releases")
heading(s, "実はつながり始めている！")
tb(s, 0.8, 1.45, W - 1.6, 0.5, "MCP Apps SDK v2.1.0（2026年11月10日）に、WebMCPとの相互運用が入りました。",
   size=22)
label_box(s, 0.9, 2.7, 4.6, 1.8, "MCP Apps\nApp.registerTool()", size=26)
label_box(s, 7.8, 2.7, 4.6, 1.8, "WebMCP\ndocument.modelContext", size=26)
arrow(s, 5.5, 3.6, 7.8, 3.6, both=True)
tb(s, 5.4, 2.85, 2.5, 0.6, "SDKが橋渡し", size=20, color=CYAN, bold=True, align=PP_ALIGN.CENTER)
tb(s, 5.4, 3.75, 2.5, 0.6, "既定で有効", size=18, color=GRAY, align=PP_ALIGN.CENTER)
tb(s, 0.9, 5.3, W - 1.8, 0.6, "通信プロトコルは変えず、SDK側で相互接続", size=24)

# ---------------------------------------------------------------- 18 締め
s = new_slide(
    "【約20秒】\n"
    "行動を促して終わる。QRコードを置く（stapy商店 https://stapy.studiooverdrive.com/ とリポジトリ）。\n"
    "公開デモは認証なしの共有カートなので、QRはこの最後のスライドで初めて出す。")
tb(s, 0.8, 1.2, W - 1.6, 2.4, "まずは自分のサイトで\nregisterTool してみませんか？", size=44,
   bold=True, color=CYAN, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
panel(s, 4.4, 4.1, 4.5, 2.4)
tb(s, 4.4, 4.1, 4.5, 2.4, "QRコード\n（stapy商店・リポジトリ）", size=22, color=GRAY,
   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

prs.save(OUT)
print("saved", OUT, len(prs.slides._sldIdLst), "slides")
