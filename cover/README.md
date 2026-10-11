# 视频封面

B站投稿封面，代码渲染生成，与视频画面风格统一。

| 文件 | 说明 |
|------|------|
| `cover_c.html` | **朴素版**：纯白底、两行大字、无价格无卡片（当前主推） |
| `cover_a.html` | 白底版：含榜单卡片（套餐名/价格/评分） |
| `cover_b.html` | 红底版：麦当劳红 + 黄色大字，信息流里最抢眼 |
| `make_cover.py` | 渲染脚本：Playwright + 系统 Chrome 截图 |

## 规格

- **尺寸**：1146 × 717（B站官方推荐，比例完全匹配，上传后无需裁剪）
- **输出**：2x 分辨率 2292 × 1434，约 90–200 KB

## 重新生成

```bash
cd cover
"C:/Users/AppleRepair/.workbuddy/binaries/python/envs/default/Scripts/python.exe" make_cover.py
```

输出到项目根目录：`视频封面_朴素版.png`、`视频封面_白底版.png`、`视频封面_红底版.png`

## 改内容

直接改 HTML 里的文字/CSS 即可，关键元素：

- 朴素版（cover_c）：顶部 `.brand`（品牌名）、主标题 `.l1` / `.l2`、底部 `.foot`
- 白底/红底版（cover_a/b）：主标题 `.l1` / `.l2`、榜单卡片 `.card` 内 `.meal` / `.price` / `.score`
- 配色：品牌红 `#DA291C`、品牌黄 `#FFC72C`
