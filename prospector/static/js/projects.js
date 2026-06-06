/**
 * 项目管理模块
 */

async function loadProjects() {
  try {
    const resp = await fetch('/api/projects');
    const data = await resp.json();
    renderProjectSelector(data.projects || []);
  } catch (e) {
    console.warn('加载项目列表失败:', e);
  }
}

function renderProjectSelector(projects) {
  const sel = Utils.$('#projectSelect');
  if (!sel) return;
  sel.innerHTML = '<option value="">无（独立任务）</option>' +
    projects.map(p => `<option value="${p.id}">${p.name} (${p.task_count} 个任务)</option>`).join('');
}

async function createProject() {
  const name = prompt('输入项目名称:');
  if (!name || !name.trim()) return;
  const desc = prompt('项目描述（可选）:', '') || '';

  try {
    const resp = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), description: desc.trim() }),
    });
    const data = await resp.json();
    if (data.error) { alert(data.error); return; }
    loadProjects();
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
}
