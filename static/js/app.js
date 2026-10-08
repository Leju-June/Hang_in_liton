// 행인(HANG-IN) 화면 동작 — 프레임워크 없이 작은 스크립트만 사용
(function () {
  'use strict';

  // 토스트 자동 숨김
  document.querySelectorAll('.toast-item').forEach(function (el, i) {
    setTimeout(function () {
      el.classList.add('is-hiding');
      setTimeout(function () { el.remove(); }, 400);
    }, 3200 + i * 400);
  });

  // 제출 시 로딩 오버레이 (AI 분석처럼 오래 걸리는 요청)
  document.querySelectorAll('form[data-loading]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (e.defaultPrevented || !form.checkValidity()) return;
      var overlay = document.getElementById(form.dataset.loading);
      if (overlay) overlay.classList.add('is-on');
      form.querySelectorAll('button[type=submit]').forEach(function (b) { b.disabled = true; });
    });
  });
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('.loading-overlay.is-on').forEach(function (o) { o.classList.remove('is-on'); });
    document.querySelectorAll('form[data-loading] button[type=submit]').forEach(function (b) { b.disabled = false; });
  });

  // 숫자 스테퍼 (+/-)
  document.querySelectorAll('[data-stepper]').forEach(function (box) {
    var input = box.querySelector('input');
    var label = box.querySelector('.stepper__value');
    var min = Number(input.min || 1), max = Number(input.max || 99);
    function render() { if (label) label.textContent = input.value + (box.dataset.unit || ''); }
    box.querySelectorAll('[data-step]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var v = Math.min(max, Math.max(min, Number(input.value || min) + Number(btn.dataset.step)));
        input.value = v;
        render();
      });
    });
    render();
  });

  // 사진 업로드: 휴대폰 사진을 2000px 이하 JPEG로 줄여서 올림 (HCX-005 이미지 제한 대응) + 미리보기
  document.querySelectorAll('input[type=file][data-resize]').forEach(function (input) {
    var maxSide = Number(input.dataset.resize) || 2000;
    var preview = input.dataset.preview ? document.getElementById(input.dataset.preview) : null;
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file || !/^image\//.test(file.type)) return;
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        if (preview) {
          preview.src = url;
          preview.hidden = false;
          var box = preview.closest('.scan');
          if (box) box.classList.add('has-image');
        }
        var scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        if (scale === 1 && /jpe?g|png/.test(file.type) && file.size < 4 * 1024 * 1024) return;
        var canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) {
          if (!blob || typeof DataTransfer === 'undefined') return;
          var dt = new DataTransfer();
          dt.items.add(new File([blob], 'photo.jpg', { type: 'image/jpeg' }));
          input.files = dt.files;
        }, 'image/jpeg', 0.88);
      };
      img.src = url;
    });
  });

  // 공유하기: Web Share API → 클립보드 복사
  document.querySelectorAll('[data-share]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.dataset.share;
      if (navigator.share) {
        navigator.share({ title: '행인 정산', text: text }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () { flash('정산 내용을 복사했어요.'); });
      }
    });
  });

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (navigator.clipboard) navigator.clipboard.writeText(btn.dataset.copy).then(function () { flash('복사했어요.'); });
    });
  });

  function flash(message) {
    var box = document.querySelector('.toasts');
    if (!box) {
      box = document.createElement('div');
      box.className = 'toasts';
      document.body.appendChild(box);
    }
    var el = document.createElement('div');
    el.className = 'toast-item toast-item--success';
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () { el.classList.add('is-hiding'); setTimeout(function () { el.remove(); }, 400); }, 2400);
  }

  // 온보딩 단계 이동 (소개 → 여행 → 숙소 → 이동)
  var wizard = document.querySelector('[data-wizard]');
  if (wizard) {
    var steps = Array.prototype.slice.call(wizard.querySelectorAll('.step'));
    var bars = Array.prototype.slice.call(wizard.querySelectorAll('.progress i'));
    var current = 0;
    function update() {
      steps.forEach(function (s, i) { s.classList.toggle('is-on', i === current); });
      bars.forEach(function (b, i) { b.classList.toggle('is-on', i < current); });
      var step = steps[current];
      var next = step.querySelector('[data-next]');
      if (next && step.dataset.required) next.disabled = !step.querySelector('input:checked');
      window.scrollTo(0, 0);
    }
    wizard.addEventListener('change', update);
    wizard.querySelectorAll('[data-next]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.type === 'submit') return;
        current = Math.min(steps.length - 1, current + 1);
        update();
      });
    });
    wizard.querySelectorAll('[data-back]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        current = Math.max(0, current - 1);
        update();
      });
    });
    update();
  }
})();
