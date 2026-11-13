# 每日市场模板（网页版）

> 在线：https://sean-daniel.github.io/market-daily-snapshot/

打开网页自动出五行结果，不需要调用 AI：

```text
深圳指数日macd：+153.00
创业板指数日macd：+49.80
上证恐贪指数：22.25，上证恐贪指数近45日高点：50.49
纳斯达克指数日macd：-45.41
纳指恐贪指数：39.94，纳指恐贪指数的近45日高点：47.03
```

## 数据怎么来的

| 数据 | 来源 | 方式 |
|---|---|---|
| 三个指数的日K | 腾讯行情 `web.ifzq.gtimg.cn` | 浏览器直接请求（该接口带 `Access-Control-Allow-Origin: *`），本地按 12/26/9 算 MACD |
| 上证/纳指恐贪指数 | 韭圈儿 `app.jiucaishuo.com` | GitHub Actions 每天定时用 Playwright 打开页面，读取 ECharts 的 `series[0]`，写进 `data/fear.json` |

恐贪页面的历史接口返回加密字符串，且接口没有 CORS 头，静态页面无法直接取，所以用 Actions 每天落一次数据（页面本身仍是纯静态）。

## 目录

```text
index.html                      页面本体（无构建、无依赖）
data/fear.json                  恐贪快照，Actions 每天覆盖
scripts/fetch_fear.py           Playwright 抓取脚本
.github/workflows/update-fear.yml  定时任务：15:40 / 08:10（北京时间）
```

## 本地预览

```bash
python3 -m http.server 8787
# 打开 http://localhost:8787
```

直接双击 `index.html` 时浏览器会拦截本地 JSON 读取，请用上面的本地服务器。

## 口径

- MACD：日线 12/26/9，`DIF=EMA12-EMA26`，`DEA=EMA(DIF,9)`，柱=`2*(DIF-DEA)`；页面显示柱值，悬停可看 DIF/DEA。
- 深圳指数=深证成指，创业板指数=创业板指，纳指=纳斯达克100（`NDX`）。
- A股盘中（15:00 前）的日K未收盘，MACD 是暂定值，页面会标注“盘中 · 暂定”。
- 恐贪指数取页面原始两位小数（如 22.25），不用顶部四舍五入的整数。
- 近45日高点取恐贪指数自身最近 45 个数据点的最高值。

## 更新恐贪数据

Actions 会在每个工作日 15:40 和次日 08:10（北京时间）自动跑。也可以手动触发：

GitHub 仓库 → Actions → 更新恐贪数据 → Run workflow。

若某天抓取失败，工作流会保留上一次的数据并在 JSON 里标 `stale`，页面仍可打开。
