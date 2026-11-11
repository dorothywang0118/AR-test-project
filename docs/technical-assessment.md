# 技術評估報告（階段一）

> 狀態：**MindAR 為候選技術，尚未鎖定。** 鎖定條件是 iPhone 與 Android 實機通過 `docs/testing.md` 的驗收門檻。
> 評估日期：2026-11-12。外部資訊來自網路搜尋，「未能確認」的項目已標明。

## 1. AR 引擎比較

| 方案 | 授權／費用 | 優點 | 風險／未確認 |
|---|---|---|---|
| **MindAR + Three.js**（POC 使用） | MIT，免費 | 純前端、圖像可多目標、可離線編譯辨識資料、可直接放 GLB | npm 最新版 1.2.5；**未能確認近期更新頻率**。核心依賴 TensorFlow.js（WebGL），低階 Android 效能需實測 |
| 8th Wall 開源版 | 引擎框架 MIT，免費 | 含 image targets 模組與圖案處理命令列工具 | 2026/2/28 才完成開源轉型，專案很新；SLAM 為封閉二進位檔（本專案用不到） |
| AR.js（NFT） | MIT，免費 | 歷史久、社群大 | 無臉部追蹤與 SLAM；依一般了解，圖像追蹤穩定度通常不如 MindAR（**待實測**） |
| Zappar Universal AR | 商業授權 | 官方明確列出 iOS 11.3+ Safari、Android Chrome、iOS 14.3+ WKWebView | 需付費方案，不符合「全部免費」原則（商業條款未查證） |

**結論：** 以 MindAR 為 POC 引擎，包在 `AREngineAdapter` 後面；若實機測試不達標，備案為 8th Wall 開源版或 AR.js，更換時只需新增一個 Adapter。

## 2. 實作 POC 時查證到的事實（已用原始碼／實際執行確認）

1. **Node 版編譯器無法安裝**：`mind-ar` 依賴原生套件 `canvas`，在本環境 `npm install` 會失敗。
   → 對策：`frontend/customer/.npmrc` 設為 `ignore-scripts=true`；辨識資料改用**瀏覽器內編譯**（`tools/compile_target.py`，已成功編譯並產出 `.mind`，約 770 KB）。這也決定了未來後台（F09）第一版採「在管理員瀏覽器內編譯再上傳」。
2. **three.js 必須固定版本**：MindAR 1.2.5 原始碼使用 `sRGBEncoding`，較新的 three.js 版本已移除，故鎖定 `three@0.160.0`（MindAR 官方文件示範的版本）。升級 three.js 前須重新測試。
3. **MindAR 的 `stop()` 釋放不完整**：只停相機與追蹤，不會釋放 WebGL、Web Worker、DOM；且 `resize` 事件監聽無法移除。
   → `MindARAdapter.dispose()` 已補齊（停止相機軌、`controller.dispose()`、`renderer.dispose()`、`forceContextLoss()`、移除 DOM）。**TensorFlow.js 的 GPU 記憶體是否完全釋放，必須在實機重複「開始／結束」多次來驗證。**
4. **相機失敗時 MindAR 不回報原因**（只 reject 空值）。→ Adapter 先自行探測相機，才能分辨「權限被拒」與「找不到相機」，顯示正確指引。
5. **體積**：引擎約 365 KB（gzip）＋ three.js 149 KB ＋ 辨識資料 770 KB。首頁不載入引擎，按下「開始」才載入（程式碼分割），以符合 5 秒載入目標。

## 3. 目前已驗證與尚未驗證

| 項目 | 狀態 |
|---|---|
| 相機啟動、辨識圖案、GLB 顯示、動畫、點擊互動、停止釋放、重新開始 | ✅ 於無頭 Chrome＋模擬相機通過（`tools/smoke_test.py`） |
| iPhone Safari 實機 | ❌ **尚未測試** |
| Android Chrome 實機 | ❌ **尚未測試** |
| LINE 內建瀏覽器 | ❌ 尚未測試 |
| 多圖案同時追蹤效能 | ❌ 尚未測試（規格要求先驗證單一圖案） |

模擬測試只證明程式流程正確，**不能取代實機驗收**（規格書 §10.2）。

## 4. 風險清單

| # | 風險 | 影響 | 對策 |
|---|---|---|---|
| R1 | iOS Safari 對 WebGL／相機的限制或效能不足 | 核心功能不可用 | 實機測試；不達標換引擎（Adapter 已隔離） |
| R2 | 低階 Android 效能不足（TF.js） | 畫面卡頓 | 調整 `maxTrack`、輸入解析度；測試至少一支中低階機型 |
| R3 | 重複開關造成記憶體增加 | 長時間使用閃退 | 實機重複 10 次開始／結束並觀察 |
| R4 | LINE 等內建瀏覽器限制相機 | 顧客掃 QR 後打不開 | 偵測並提示改用 Safari／Chrome；實機驗證 |
| R5 | 店員自行換的圖案特徵不足 | 辨識不穩 | 後台上傳時做品質檢查並預覽辨識；提供製圖指南 |
| R6 | MindAR 維護停滯 | 長期相容性 | Adapter 隔離；三方版本固定；保留備案 |
| R7 | Nintendo IP 未授權 | 法律風險 | 僅用原創素材；上線前須公司確認授權 |
| R8 | 免費額度（Supabase 等）不足或閒置暫停 | 後台／API 中斷 | 階段四前重新確認最新免費規則 |

## 4.1 規格書需要補強之處

1. **版本綁定**：規格 §6 的 `Experiences` 未綁定 `Campaign Version`，無法保證「發布才切換、可回復」。建議每個版本產生**不可變 manifest 快照**（見 `shared/types/campaign.ts`），素材用內容雜湊命名。
2. **辨識資料粒度**：MindAR 將多個圖案編成**一個** `.mind` 檔，與規格 §6.2 每個 Target 一個 `tracking_asset_url` 不同。manifest 改為活動層級的 `trackingAsset` ＋ `targetOrder`。
3. **互動動畫**：規格範例只有單一 `interaction_animation`；POC 改為清單（Wave、Jump 輪流）。
4. **狀態轉換規則**：見 `architecture.md` §4 草案，待你確認。

## 5. 建議技術組合（Prototype）

React + TypeScript + Vite（後台階段再引入 React；POC 為原生 TypeScript 以降低變數）、MindAR + Three.js（候選）、GLB、Supabase 免費方案（階段四）、GitHub Pages／Cloudflare Pages 免費託管。
