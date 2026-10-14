---
marp: true
theme: default
size: 16:9
paginate: true
title: "学習課題の変更：コンビニの入口制御から2室の換気制御へ"
description: "変更前の問題、変更後の問題、難易度の比較と実験の時間配分"
style: |
  section {
    display: block;
    padding: 40px 54px 46px;
    background: white;
    color: #111;
    font-family: 'Noto Sans JP', 'Yu Gothic', 'Meiryo', sans-serif;
    font-size: 24px;
    line-height: 1.5;
  }
  h1 { color: #111; font-size: 36px; margin: 0 0 20px; padding-bottom: 12px; border-bottom: 2px solid #111; }
  h2 { color: #111; font-size: 25px; margin: 0 0 14px; }
  p { margin: 0 0 16px; }
  strong { color: #111; }
  .lead { margin-bottom: 22px; }
  .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 34px; }
  .specs { display: grid; grid-template-columns: 1fr 1.15fr 1fr; gap: 22px; margin-top: 20px; }
  .spec { border: 1px solid #888; padding: 18px; font-size: 22px; }
  .spec h2 { font-size: 24px; border-bottom: 1px solid #aaa; padding-bottom: 10px; }
  .spec p { margin-bottom: 14px; }
  .spec p:last-child { margin-bottom: 0; }
  .small { font-size: 19px; line-height: 1.5; }
  .note { border-top: 1px solid #aaa; padding-top: 12px; margin-top: 18px; font-size: 22px; }
  .rule { padding: 12px 16px; border: 1px solid #888; margin-bottom: 12px; font-size: 23px; }
  .columns h2:not(:first-child) { margin-top: 24px; }
  table { display: table; width: 100%; font-size: 23px; margin: 0; border-collapse: collapse; }
  table th, table td { padding: 10px 14px; border: 1px solid #aaa; }
  table th { background: #eee; color: #111; }
  table tr { background: white; }
  .comparison-table { font-size: 21px; }
  .comparison-table th:first-child { width: 16%; }
  .comparison-table th:nth-child(2) { width: 32%; }
  .comparison-table td, .comparison-table th { padding: 8px 14px; }
  .example { margin-top: 20px; border: 1px solid #888; padding: 14px 18px; }
  .example h2 { font-size: 23px; margin-bottom: 10px; }
  .example .columns { gap: 20px; font-size: 23px; }
  .example p { margin: 0; }
  .time-table { font-size: 20px; }
  .time-table th:first-child { width: 30%; }
  .time-table th:nth-child(2) { width: 10%; }
  .time-table td, .time-table th { padding: 7px 14px; }
  section::after { right: 54px; bottom: 15px; color: #555; font-size: 14px; }
---

# 変更前：コンビニの入口制御

<p class="lead"><strong>人が来たら自動ドアを開ける。</strong><br>さらに、<strong>夜に人が来たときだけチャイムを鳴らす。</strong></p>

<div class="columns">
<div>
<h2>使える情報と動作</h2>
<p>入力：人の有無、昼／夜<br>出力：ドアの開閉、チャイムの鳴動</p>
<h2>条件と動作を組み合わせる</h2>
<div class="rule">人がいる → ドアを開ける</div>
<div class="rule">人がいる <strong>AND</strong> 夜である<br>→ チャイムを鳴らす</div>
</div>
<div>
<h2>確認する4つの場面</h2>
<table>
<thead><tr><th>場面</th><th>ドア</th><th>チャイム</th></tr></thead>
<tbody>
<tr><td>昼・人あり</td><td>開く</td><td>鳴らない</td></tr>
<tr><td>昼・人なし</td><td>閉じる</td><td>鳴らない</td></tr>
<tr><td>夜・人あり</td><td>開く</td><td>鳴る</td></tr>
<tr><td>夜・人なし</td><td>閉じる</td><td>鳴らない</td></tr>
</tbody>
</table>
<p class="note">その場の2つの条件を見て判断する。<br><strong>過去の状態を記憶する必要はない。</strong></p>
</div>
</div>

<!--
変更前のアプリに実装された問題を整理したもの。
出典：README.md「元のコンビニ課題」、frontend/src/config.js、frontend/src/domain/simulation.js、backend/domain.py。
原論文の実験条件全体を再現したスライドではない。
正解例は、人感センサーでドア、人感センサー AND 明るさセンサーでチャイム、の2ルール。
「夜ならチャイム」という案では、夜に人がいなくても鳴る。このような反例を対話と実行で確かめる。
大学生には簡単すぎるという懸念から、次の換気課題へ変更した。難易度差を実験で測定したという意味ではない。
-->

---

# 変更後：2室で共有する換気装置の制御

<p class="lead">自習室A・Bの<strong>人の有無とCO₂濃度</strong>を読み、1台の装置を制御する。<br>動作は<strong>「A室を換気」「B室を換気」「停止」</strong>のいずれか。</p>

<div class="specs">
<div class="spec">
<h2>① 数値で示す目的</h2>
<p><strong>連続未対応は4ステップ以内</strong><br>有人・1,000ppm以上が対象</p>
<p><strong>不要な運転は0回</strong><br>無人室・800ppm以下への運転</p>
<p><strong>改善目標：高濃度への対応</strong><br><span class="small">1,500ppm以上の未対応時間を<br>同じ入力で修正前より減らす</span></p>
</div>
<div class="spec">
<h2>② 装置の制限：違反0回</h2>
<p><strong>装置は1台</strong><br>両室の同時換気はできない</p>
<p><strong>2ステップ連続で運転</strong><br>→ 次の1ステップは停止</p>
<p><strong>別室への切り替え</strong><br>→ 間に1ステップ停止</p>
<p><strong>点検中は必ず停止</strong></p>
</div>
<div class="spec">
<h2>③ 学習者が考えること</h2>
<p><strong>換気を始める・終える条件</strong></p>
<p><strong>どちらの部屋を優先するか</strong></p>
<p><strong>前回の状態や待ち時間を<br>どのように使うか</strong></p>
<p class="small">条件や優先順位を自分で設計し、判断の理由を説明する。</p>
</div>
</div>

<!--
数値による達成基準と装置の制限を提示し、制御条件と優先方針を学習者が考える課題。
有人かつ1,000ppm以上の連続未対応は4ステップ以内、無人または800ppm以下への運転は0回、装置制約違反は0回。
未対応は換気・退室・1,000ppm未満・点検でリセット。停止制約の時間も含める。
1,500ppm以上の有人室が未対応だった延べ部屋ステップ数は、同じ入力・同じ実行範囲で修正前後を比較する。
修正前から0なら維持し、改善の余地がないことを説明する。
これらを達成するON/OFF条件や、濃度・待ち時間・継続の優先順は指定しない。
同じ濃度でも過去の状態を使う設計は考えられるが、それを必須の正解にはしない。
シミュレーションは濃度の入力列から装置の割り当てを観測し、濃度低下の物理計算は行わない。
出典：docs/high_difficulty_task.md、backend/ventilation_content.py。
-->

---

# 難しくした点：過去の状態と優先順位も考える

<table class="comparison-table">
<thead><tr><th>観点</th><th>変更前：コンビニ</th><th>変更後：換気</th></tr></thead>
<tbody>
<tr><td>入力</td><td>人の有無・昼夜</td><td>2室の人の有無・濃度・点検モード</td></tr>
<tr><td>覚える状態</td><td>なし</td><td>換気要求・待ち時間・前回動作・連続運転数</td></tr>
<tr><td>判断</td><td>真偽値とAND条件</td><td>数値・履歴を使い、条件と優先方針を設計</td></tr>
<tr><td>検証</td><td>昼夜 × 人の有無の4場面</td><td>数値基準の達成と修正前後の未対応時間を比較</td></tr>
</tbody>
</table>

<div class="example">
<h2>例：濃度が高い部屋への対応と、他室の待ち時間が競合したら？</h2>
<div class="columns">
<p><strong>濃度を重視する案</strong><br>もう一方を待たせすぎないか？</p>
<p><strong>待ち時間を重視する案</strong><br>高い濃度への対応は十分か？</p>
</div>
<p class="small" style="margin-top: 8px;">未対応4ステップ以内・不要な運転0回・制約違反0回を満たす条件を設計し、改善と判断の根拠を比較する。</p>
</div>

<!--
異なる優先方針を唯一の出力列で採点しない。
数値基準の達成、判断の説明と修正を検討する。途中の結果は実行済みの範囲だけの達成状況。
参考待ち時間は、学習者の換気要求とは独立に有人かつ目安以上の未対応時間を数える。
未対応には装置の停止制約による時間も含めて4ステップ以内か確認する。
出典：docs/high_difficulty_task.md、backend/ventilation_engine.py。
-->

---

# 実験の時間配分：全体90分

<p class="lead"><strong>課題本体60分</strong> ＋ 説明・アンケート20分 ＋ 予備時間10分</p>

<table class="time-table">
<thead><tr><th>内容</th><th>時間</th><th>主な活動</th></tr></thead>
<tbody>
<tr><td>事前アンケート</td><td>5分</td><td>実験前の回答</td></tr>
<tr><td>課題・操作説明、練習</td><td>10分</td><td>目的・制限の確認、画面操作の練習</td></tr>
<tr><td>① 1人で考える</td><td>15分</td><td>条件と優先方針を考え、最初のプログラムを作る</td></tr>
<tr><td>② ペアで対話する</td><td>10分</td><td>AIに判断理由を説明し、見落とした場面を考える</td></tr>
<tr><td>③ 実行して確認する</td><td>20分</td><td>予想と結果を比較し、複数シナリオで検証・修正</td></tr>
<tr><td>④ 全体で対話する</td><td>15分</td><td>他の案と比較し、最終修正と振り返りを行う</td></tr>
<tr><td>事後アンケート</td><td>5分</td><td>実験後の回答</td></tr>
<tr><td>予備時間</td><td>10分</td><td>操作のつまずき・進行調整への対応</td></tr>
<tr><td><strong>合計</strong></td><td><strong>90分</strong></td><td><strong>操作説明・事前事後アンケート・予備時間を含む</strong></td></tr>
</tbody>
</table>

<!--
時間配分は実測結果ではなく、全体90分を上限とする実験計画の案。
4フェーズの合計は15＋10＋20＋15＝60分。
8種類のシナリオを検証対象に残し、各フェーズの所要時間と到達状況を予備実験で確認する。
予備時間10分は必要に応じて使用し、早く終了した参加者に時間いっぱいまで作業を求めない。
-->
