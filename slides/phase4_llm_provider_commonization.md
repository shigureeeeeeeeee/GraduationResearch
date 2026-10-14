---
marp: true
theme: graduation-research
size: 16:9
paginate: false
title: "フェーズ4：LLMプロバイダーの共通化"
description: "グループ別LLM割り当て機能の変更概要"
---

<!-- _class: provider-commonization -->

<header class="slide-header">
<div>
<h1>LLMプロバイダーの共通化</h1>
</div>
</header>

<main class="comparison">
<article class="panel before-panel">
<div class="panel-heading">
<h2>変更前</h2>
<span>プロバイダー依存</span>
</div>
<div class="before-flow">
<div class="agent-stack">
<span class="agent agent-a">A</span>
<span class="agent agent-b">B</span>
<span class="agent agent-c">C</span>
<span class="agent agent-f">司会</span>
</div>
<span class="flow-arrow muted-arrow">→</span>
<div class="service old-service"><strong>Ollama</strong><small>直呼び出し</small></div>
</div>
<ul class="issue-list">
<li>フェーズ4はOllama専用</li>
<li>全グループが同じモデル</li>
</ul>
</article>
<div class="change-arrow">›</div>
<article class="panel after-panel">
<div class="panel-heading">
<h2>変更後</h2>
<span>共通インターフェース</span>
</div>
<div class="after-flow">
<div class="agent-stack">
<span class="agent agent-a">A</span>
<span class="agent agent-b">B</span>
<span class="agent agent-c">C</span>
<span class="agent agent-f">司会</span>
</div>
<span class="flow-arrow">→</span>
<div class="service common-client"><strong>共通 LLM Client</strong><small>同じ形式で呼び出し</small></div>
<span class="flow-arrow">→</span>
<div class="provider-stack">
<div class="service ollama"><strong>Ollama</strong></div>
<div class="service gemini"><strong>その他のLLM</strong></div>

</div>
</div>
</article>
</main>

<section class="outcomes">
</section>

