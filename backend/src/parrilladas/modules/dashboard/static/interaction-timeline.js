(() => {
  const chart = document.querySelector('.interaction-timeline');
  if (!chart) return;
  const points = JSON.parse(chart.dataset.points || '[]');
  const svg = chart.querySelector('svg');
  const line = chart.querySelector('.timeline-line');
  const dots = chart.querySelector('.timeline-dots');
  const labels = chart.querySelector('.timeline-labels');
  const grid = chart.querySelector('.timeline-grid');
  if (!points.length) {
    chart.querySelector('.timeline-empty').hidden = false;
    return;
  }
  const width = 900, height = 260;
  const left = 38, right = 18, top = 20, bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const max = Math.max(...points.map((point) => point.count), 1);
  const x = (index) => left + (index / Math.max(points.length - 1, 1)) * plotWidth;
  const y = (value) => top + plotHeight - (value / max) * plotHeight;
  line.setAttribute('points', points.map((point, index) => `${x(index)},${y(point.count)}`).join(' '));
  [0, .5, 1].forEach((ratio) => {
    const value = Math.round(max * ratio);
    const yPos = y(value);
    const horizontal = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    horizontal.setAttribute('x1', left); horizontal.setAttribute('x2', width - right);
    horizontal.setAttribute('y1', yPos); horizontal.setAttribute('y2', yPos);
    horizontal.classList.add('timeline-grid-line'); grid.appendChild(horizontal);
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', 4); text.setAttribute('y', yPos + 4); text.textContent = value;
    text.classList.add('timeline-axis-label'); grid.appendChild(text);
  });
  points.forEach((point, index) => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x(index)); circle.setAttribute('cy', y(point.count)); circle.setAttribute('r', 4);
    circle.setAttribute('tabindex', '0'); circle.setAttribute('aria-label', `${point.day}: ${point.count} interacciones`);
    circle.classList.add('timeline-dot'); dots.appendChild(circle);
  });
  const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  labelIndexes.forEach((index) => {
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x(index)); text.setAttribute('y', height - 12); text.setAttribute('text-anchor', index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle');
    text.textContent = points[index].day.slice(5).split('-').reverse().join('/');
    text.classList.add('timeline-axis-label'); labels.appendChild(text);
  });
})();
