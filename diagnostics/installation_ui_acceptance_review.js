// Isolated rendering checks; inert markup only, no browser or network calls.
const fs = require('fs'), path = require('path'), vm = require('vm');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'master_hub/static/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'master_hub/static/app.js'), 'utf8');
const table = {innerHTML: ''};
const context = vm.createContext({document: {getElementById: () => table}, console});
vm.runInContext(source.slice(source.indexOf('let installationPollTimer = null;')), context);
let failures = 0;
function check(name, condition) {
    console.log(`${condition ? 'PASS' : 'FAIL'}: ${name}`);
    if (!condition) failures++;
}
check('Installation table is present in the actual dashboard page', /id=["']installationsTableBody["']/.test(html));
context.renderInstallationsDashboard([], [{
    id: 'test-attempt', architecture: 'x64', release_version: '1', current_stage: 'FAILED',
    total_bytes: 10, download_bytes: 1, error_code: 'TEST',
    error_detail: '<review-marker>must be text</review-marker>', updated_at: new Date().toISOString()
}]);
check('Untrusted diagnostic text is rendered as text, not HTML', !table.innerHTML.includes('<review-marker>'));
process.exitCode = failures ? 1 : 0;
