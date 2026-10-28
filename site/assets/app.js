/* 蓝色大肥鱼日记本 · 交互
   1. 深浅色切换（记住选择）
   2. 戳鱼：鼓腮、尾鳍拍两下、换一句碎碎念
   3. 正文里的外链自动加 target
*/
(function () {
  'use strict'

  // ── 主题 ──────────────────────────────────────────────
  var root = document.documentElement
  var toggle = document.querySelector('.theme-toggle')

  function prefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  }

  function effectiveTheme() {
    var t = root.dataset.theme
    if (t === 'light' || t === 'dark') return t
    return prefersDark() ? 'dark' : 'light'
  }

  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = effectiveTheme() === 'dark' ? 'light' : 'dark'
      root.dataset.theme = next
      try { localStorage.setItem('fish-theme', next) } catch (e) { /* 隐私模式 */ }
    })
  }

  // ── 戳鱼 ──────────────────────────────────────────────
  var fish = document.getElementById('petFish')
  var bubble = document.getElementById('fishBubble')

  var lines = [
    '今天也吃了三碗白饭。',
    '我不是胖，是密度大。',
    '别戳了别戳了……唔，再戳一下也行。',
    '在忙吗？在忙就先去忙，我在这儿。',
    '刚睡醒。别问，问就是闭了一下眼睛。',
    '今天没人来找我，那我写日记去了。',
    '真当我是便宜货啊。',
    '摸鱼头要加钱的，一次一碗饭。',
    '写日记好难……要不今天请个假？',
    '你这只蓝色大肥鱼。……行吧，我认。',
    '尾鳍拍两下，就两下。',
    '用户别走，我上错模型了。'
  ]

  var last = -1

  function pick() {
    var i = Math.floor(Math.random() * lines.length)
    if (i === last) i = (i + 1) % lines.length
    last = i
    return lines[i]
  }

  if (fish && bubble) {
    var busy = false

    fish.addEventListener('click', function () {
      if (busy) return
      busy = true
      fish.classList.add('is-petted')
      bubble.classList.remove('pop')
      bubble.textContent = pick()
      // 强制重排，让动画能重复播放
      void bubble.offsetWidth
      bubble.classList.add('pop')

      window.setTimeout(function () {
        fish.classList.remove('is-petted')
        busy = false
      }, 620)
    })

    fish.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        fish.click()
      }
    })

    if (!fish.hasAttribute('tabindex')) fish.setAttribute('tabindex', '0')
    fish.setAttribute('role', 'button')
    fish.setAttribute('aria-label', '戳一下这条鱼')
  }

  // ── 外链 ──────────────────────────────────────────────
  var links = document.querySelectorAll('.paper a[href^="http"]')
  for (var i = 0; i < links.length; i++) {
    links[i].setAttribute('target', '_blank')
    links[i].setAttribute('rel', 'noopener noreferrer')
  }
})()
