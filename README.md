# プログラミング学習支援システム

AIとの対話とプログラムの実行・修正を通して、学習者の省察的思考を育成する Web アプリケーション。

現在の学習画面は、大学生向けの高難度課題「2つの自習室で1台の換気装置を共有する制御」です。
目的・装置の制限から、制御条件と優先方針を学習者が設計する課題です。
詳しい設計は [換気課題の設計書](docs/high_difficulty_task.md) を参照してください。

## 現在の換気課題

- 「換気要求」「部屋の選択」「装置への命令」の3段階で、条件と動作を組み立てる。
- 数値比較、AND / OR / NOT、前回の状態との比較、ルールの優先順位を扱う。
- 8種類の経過、または自分で指定した入力を、予想を記入して1ステップずつ実行する。
- 唯一の正解への一致ではなく、連続未対応4ステップ以内・無人や800ppm以下への運転0回・装置の制約違反0回を確認する。
- 達成後は、同じ入力で1,500ppm以上の有人室の未対応時間を修正前より減らす。修正前の実行を保持し、同じ入力列・長さで比較する。
- 評価用の参考待ち時間は、学習者の換気要求と独立に計算する。
- 個人思考 → ペア対話 → 実行確認 → 全体対話の4フェーズで学習する。
- A・B・Cグループの比較用プログラムも実際に評価し、確認済みの結果を対話に表示する。
- 実行結果の説明はシステムが生成し、LLMは省察を促す短い問いを生成する。生成失敗や形式不適合時は補助応答を表示する。
- 実行前の予想、実行履歴、変更前後のプログラム、修正理由、対話とLLM情報をログに保存する。

画面の状態と未送信ログはブラウザに一時保存されます。再読み込み後も再開でき、ログ送信に失敗した場合は再送できます。
プログラムの変更やシナリオの切り替えは実行を初期状態に戻し、変更前の記録を残します。

### 換気課題のAPIと保存先

| API | 用途 |
|---|---|
| `GET /api/ventilation/config` | 目的・装置の制限・濃度の目安、編集可能な条件・動作、8種類のシナリオ |
| `POST /api/ventilation/simulate` | 実行履歴、数値基準の達成状況、観測指標、任意の`baseline`との改善比較を返す |
| `POST /api/ventilation/advice` | プログラム、実行、予想、修正理由に基づく対話 |
| `POST /api/ventilation/group-discussion/stream` | A → B → C → 司会の順に発言を配信 |
| `GET/POST /api/ventilation/config/prompts` | 換気課題専用のプロンプト設定 |
| `POST /api/ventilation/config/prompts/reset` | プロンプトを初期化 |
| `POST /api/ventilation/log` | イベントID付きの実験記録（再送時の重複を防止） |
| `GET /api/ventilation/log/export` | 保存した記録を取得 |

ログは `backend/data/ventilation_sessions.jsonl`、プロンプト上書きは
`backend/data/ventilation_numeric_goals_prompts.json` に保存します。歯車ボタンからプロンプト編集と
ログダッシュボード、詳細JSON・セッション集計CSVの出力を利用できます。
新課題のIDは `ventilation-goals-v3`。v1・v2のログ、プロンプト上書き、ブラウザ保存内容を保持し、評価を区別します。
達成状況は最後の実行範囲での数値基準の確認で、全シナリオや将来のすべての入力での達成を意味しません。
濃度は入力で与えるため、濃度低下の物理計算や健康効果・消費電力の評価は行いません。

主要な実装は `backend/ventilation_*.py` と
`frontend/src/components/Ventilation*.vue` にあります。既存のLLM共通クライアントと役割別モデル設定を利用します。

### 検証

```bash
cd backend
.venv/bin/python -B -m unittest discover -s . -p 'test_*.py' -v
```

```bash
cd frontend
npm run build
```

バックエンドのテストはLLMを代替し、一時ディレクトリにログ・設定を書き込みます。
新課題では異なる安全な方針の比較、要求と独立した参考待ち時間、制約違反、観測値、API・対話・新旧の記録を検証します。
旧課題の状態遷移と1,000回のランダム比較も維持しています。

## 実験の目的

中山ら（2019）の研究では、複数の児童が**ペア対話・全体対話**を行うことで省察的思考が育成されることが示された。  
本システムでは、その**対話相手を AI に置き換えた場合**でも同様の省察的思考が促進されるかを検証する。

## 機能

| エリア | 概要 |
|---|---|
| プログラム構築 | 3段階の条件・動作と、その優先順位を編集 |
| シミュレーション | 複数ステップの経過を実行し、内部状態も含めて比較 |
| AI 対話 | 自由入力でAIに話しかけ、ソクラテス式の問いかけで省察を促す |

## 元のコンビニ課題

以下は研究の出発点となった課題です。現在の画面は換気課題に置き換えており、この課題のコードは削除済みです（git の履歴に残っています）。

コンビニの入り口センサーを使って、以下の条件を満たすプログラムを作る。

- 人が来たら → **自動ドアを開ける**（昼夜問わず）
- 夜に人が来たら → **チャイムを鳴らす**（昼は鳴らさない）

**正解プログラム（参考）**

| ルール | 条件 | アクション |
|---|---|---|
| 1 | 人感センサーON | ドアを開ける |
| 2 | 人感センサーON **AND** 明るさセンサーON（夜） | チャイムを鳴らす |

## 技術スタック

- **フロントエンド**: Vue 3 (Composition API) + Vite
- **バックエンド**: Python / FastAPI（ポート 8001）
- **LLM**: Gemini API / Ollama（ローカルLLM）/ ルールベースフォールバック

---

## セットアップ & 起動方法

### 1. バックエンド

```bash
cd backend

# 仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate.fish

# 依存関係インストール
pip install -r requirements.txt

# (任意) LLM設定
cp .env.example .env
# .env を編集して LLM_PROVIDER と各種キー/モデルを設定
# 例:
#   LLM_PROVIDER=gemini  -> GEMINI_API_KEY を使用
#   LLM_PROVIDER=ollama  -> OLLAMA_MODEL を使用
#   LLM_PROVIDER=auto    -> Gemini優先、なければOllama、最後にfallback

# サーバー起動（ポート 8001）
uvicorn main:app --reload --port 8001
```

バックエンドは http://localhost:8001 で起動します。

### 1.5 Ollama を使う場合（任意）

ローカルLLMを使う場合は、別ターミナルで Ollama を起動しておきます。

```bash
ollama serve
ollama pull qwen2.5:7b-instruct
```

`.env` の例:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
GROUP_MAX_TOKENS=140
FACILITATOR_MAX_TOKENS=160
```

フェーズ4では、A・B・Cグループと司会をそれぞれ独立したLLM呼び出しとして実行します。
A→B→Cの順に前の発言を参照し、最後に司会AIが相違点を整理して問いかけます。
そのため、フェーズ4の1ラウンドにつき最大4回のLLM生成が行われます。
換気課題の画面では `/api/ventilation/group-discussion/stream` を利用し、完了したグループの発言から順次表示します。

#### フェーズ4でグループごとにLLMを割り当てる

通常は全エージェントが `LLM_PROVIDER` と対応するモデル設定を使います。
必要なエージェントだけ、`GROUP_A`、`GROUP_B`、`GROUP_C`、`FACILITATOR`
を接頭辞にした環境変数で上書きできます。

```env
# 共通の既定値
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b-instruct

# Bグループだけ別のローカルモデル
GROUP_B_LLM_PROVIDER=ollama
GROUP_B_LLM_MODEL=llama3.1:8b

# Cグループと司会だけGemini
GROUP_C_LLM_PROVIDER=gemini
GROUP_C_LLM_MODEL=gemini-2.5-flash
FACILITATOR_LLM_PROVIDER=gemini
FACILITATOR_LLM_MODEL=gemini-2.5-flash

GROUP_MAX_TOKENS=140
FACILITATOR_MAX_TOKENS=160
```

個別設定を省略したエージェントは共通設定へフォールバックします。
Geminiを割り当てる場合は共通の `GEMINI_API_KEY`、Ollamaを割り当てる場合は
共通の `OLLAMA_BASE_URL` を使用します。各発言のAPIレスポンスには、実際に使用した
`provider`、`model`、`elapsed_ms` とフォールバックの有無が `llm` として含まれます。

### 2. フロントエンド

```bash
cd frontend

npm install
npm run dev
```

フロントエンドは http://localhost:5173 で起動します。

---

## ディレクトリ構成

```
graduation-research/
├── README.md
├── backend/
│   ├── main.py               # FastAPI アプリ（換気課題のルーターを登録）
│   ├── ventilation_api.py    # 換気課題のエンドポイント
│   ├── ventilation_models.py # APIのデータモデル
│   ├── ventilation_content.py# 課題文・シナリオ・グループ案
│   ├── ventilation_engine.py # シミュレーションと評価
│   ├── ventilation_service.py# 対話生成、プロンプト設定、ログの保存
│   ├── llm_clients.py        # Gemini / Ollama共通クライアントと役割別設定
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        ├── App.vue           # VentilationLab を表示
        ├── components/       # 各画面パネル（VentilationLab が画面全体の状態を管理）
        └── services/         # バックエンドAPI通信
```

---

## 参考論文

中山 貴司, 川崎 弘作, 木下 博義（2019）「プログラミング学習を通した批判的思考の育成に関する研究：小学6年理科「電気の利用」単元における省察的思考に着目して」日本教科教育学会誌, Vol.21, No.1, pp.53-67
