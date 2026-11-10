// 测的就是我们改过的那段引擎代码：同名空项目复用 / 显式绑定 / 空项目判定
// 跑法：Djian 源码目录由 DJIAN_SRC 指定（CI 里 clone 上游 + 打补丁）
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const srcDir = process.env.DJIAN_SRC;
if (!srcDir) test.skip('没有 DJIAN_SRC，跳过引擎集成测试');

const home = fs.mkdtempSync(path.join(os.tmpdir(), 'djian-test-'));
process.env.DJIAN_DATA_DIR = home;
process.env.HOME = home;

const storeUrl = pathToFileURL(path.join(srcDir, 'packages/webui/server/store.mjs')).href;
const { Store } = await import(storeUrl);
const fixed = new Date('2026-11-11T02:00:00Z');
const today = '剪辑 2026-11-11';

test('同一自动名、空项目 → 复用同一个项目（这是自建新项目的根因修复）', () => {
  const s = new Store();
  const a = s.bindSession('session-a');
  const b = s.bindSession('session-b');
  const c = s.bindSession('session-c');
  assert.equal(a, c, '同名空项目应被接手，不该每次新建');
  assert.equal(b, c);
  assert.equal(s.list().length, 1, '三个会话只应有一个空项目');
});

test('项目里有内容就不再复用，另建一个新项目', () => {
  const s = new Store();
  const first = s.create(today);
  // 手动塞一条素材，判定为"有人在用"
  fs.writeFileSync(path.join(s.assetsDir(first), 'clip.mp4'), 'x');
  const second = s.bindSession('session-d');
  assert.notEqual(second, first, '有素材的项目不能被顶替');
});

test('bindSessionTo 能把会话指到已有项目（mf dj bind 走这条）', () => {
  const s = new Store();
  const p = s.create('20261111-测试片');
  const pid = s.bindSessionTo('session-e', p);
  assert.equal(pid, p);
  assert.equal(s.sessions()['session-e'], p);
});

test('bindSessionTo 指向不存在的项目要报 404，不能默默新建', () => {
  const s = new Store();
  assert.throws(() => s.bindSessionTo('session-f', 'p-not-exist'), (e) => e.status === 404);
});

test('显式传名字时按名字复用，不同名字互不干扰', () => {
  const s = new Store();
  const a = s.bindSession('session-g', '片子A');
  const b = s.bindSession('session-h', '片子A');
  const c = s.bindSession('session-i', '片子B');
  assert.equal(a, b);
  assert.notEqual(a, c);
});
