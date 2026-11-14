// Independent of the application bundle: missing JS still gets a useful screen.
(() => {
  const shell = document.getElementById('startup-status');
  const message = document.getElementById('startup-message');
  const retry = document.getElementById('startup-retry');
  let ready = false;
  const failed = () => {
    if (ready) return;
    shell.querySelector('strong').textContent = '界面加载未完成';
    message.textContent = '可以重新加载界面；本地数据不会被清除。';
    retry.hidden = false;
  };
  const error = event => {
    if (event instanceof ErrorEvent || event.target?.tagName === 'SCRIPT') failed();
  };
  const timer = window.setTimeout(failed, 8000);
  window.addEventListener('error', error, true);
  window.addEventListener('stock-monitor-frontend-ready', () => {
    ready = true;
    window.clearTimeout(timer);
    window.removeEventListener('error', error, true);
    shell.remove();
  }, {once: true});
  // Never auto-reload a page: that could discard an in-progress user operation.
  retry.addEventListener('click', () => window.location.reload());
})();
