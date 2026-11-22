/* Monitoring uses local HTMX only; no dynamic evaluation or inline scripts. */
htmx.config.allowEval = false;
htmx.config.allowScriptTags = false;
htmx.config.includeIndicatorStyles = false;
htmx.config.historyCacheSize = 0;
document.addEventListener('htmx:beforeRequest', function (event) {
  if (document.hidden) event.preventDefault();
});
document.addEventListener('htmx:beforeSwap', function (event) {
  if ([409, 503].includes(event.detail.xhr.status)) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
document.addEventListener('visibilitychange', function () {
  var content = document.getElementById('rag-monitoring-content');
  if (!document.hidden && content) {
    htmx.ajax('GET', content.getAttribute('hx-get'), {target: content, swap: 'outerHTML'});
  }
});
