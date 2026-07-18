export const PHASES = [
  {
    id: 1,
    label: '1人で考える',
    desc: 'まずは自分でプログラムを組み立ててみよう。センサーとアクションを組み合わせてルールを作ってください。',
    showChat: false,
  },
  {
    id: 2,
    label: 'ペアで対話する',
    desc: 'AIをペアの友達として、お互いのプログラムについて話し合おう。「なぜそうしたの？」を伝え合ってみよう。',
    showChat: true,
  },
  {
    id: 3,
    label: '実行して確認する',
    desc: '4つのシナリオ（昼夜×人あり/なし）を全部シミュレーションして、正しく動くか確認しよう。',
    showChat: true,
  },
  {
    id: 4,
    label: '全体で対話する',
    desc: '他のグループの考えを見ながら、クラス全体で「どこがよいか・どこを直せそうか」を話し合おう。',
    showChat: true,
  },
]

export const PHASE_INTRO_MESSAGES = {
  2: 'こんにちは！ペアの対話フェーズだね。\nあなたのプログラム、どんなルールにした？私のと比べてみたいな。教えてくれる？',
  3: '実行して確認するフェーズだよ！\n4つの場面（昼・人あり、昼・人なし、夜・人あり、夜・人なし）を全部チェックしてみよう。全部✓になるかな？',
  4: 'ここからは全体対話だよ。\nA・B・Cの各AIグループが、それぞれの立場から順番に意見を出します。前のグループの発言も読みながら話し合うので、自分の考えも伝えて比べてみよう。',
}

export const CONDITION_OPTIONS = [
  { value: 'person_sensor', label: '人感センサーON（人がいる）' },
  { value: 'dark_sensor', label: '明るさセンサーON（夜・暗い）' },
]

export const ACTION_OPTIONS = [
  { value: 'door', label: 'ドアを開ける' },
  { value: 'bell', label: 'チャイムを鳴らす' },
]

export const CONDITION_LABELS = Object.fromEntries(
  CONDITION_OPTIONS.map(({ value, label }) => [value, label]),
)

export const ACTION_LABELS = Object.fromEntries(
  ACTION_OPTIONS.map(({ value, label }) => [value, label]),
)

export const SCENARIOS = [
  { label: '昼・人あり', personPresent: true, isDark: false },
  { label: '昼・人なし', personPresent: false, isDark: false },
  { label: '夜・人あり', personPresent: true, isDark: true },
  { label: '夜・人なし', personPresent: false, isDark: true },
]

export const GROUP_DISCUSSION_EXAMPLES = [
  {
    group: 'Aグループ',
    title: '夜ならいつでもチャイム',
    rules: ['[明るさセンサーON（夜）] → [チャイムを鳴らす]'],
    question: '夜に人が来ていないときも、チャイムは鳴ってよいかな？',
  },
  {
    group: 'Bグループ',
    title: '夜だけドアが開く',
    rules: ['[人感センサーON AND 明るさセンサーON（夜）] → [ドアを開ける]'],
    question: '昼に人が来たとき、ドアはどうなるだろう？',
  },
  {
    group: 'Cグループ',
    title: 'ドアとチャイムを同じ条件にする',
    rules: [
      '[人感センサーON] → [ドアを開ける]',
      '[人感センサーON] → [チャイムを鳴らす]',
    ],
    question: '昼に人が来たとき、チャイムまで鳴る必要はあるかな？',
  },
]
