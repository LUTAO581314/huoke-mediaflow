// host-bridge 的「会话→项目」缓存必须会在外部改绑后失效（2 秒 TTL）。
// 曾经的 bug：函数开头 `if (has) return get()` 让 TTL 永远走不到，
// 结果 mf dj bind / 删项目 / 面板切项目之后，面板工具仍指着旧项目 → "项目不存在"。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import path from 'node:path';

const SRC = process.env.DJIAN_SRC || '/tmp/djian';
const { EngineClient } = await import(path.join(SRC, 'packages/host-bridge/lib/engine-client.js'));

function fakeClient(seq) {
  const c = new EngineClient({ clientId: 'test' });
  let i = 0;
  c.posts = 0;
  c.post = async () => {
    c.posts += 1;
    return { project: { id: seq[Math.min(i++, seq.length - 1)] } };
  };
  return c;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test('2 秒内重复调用只打一次接口', async () => {
  const c = fakeClient(['p1']);
  assert.equal((await c.projectFor('s1')).id, 'p1');
  assert.equal((await c.projectFor('s1')).id, 'p1');
  assert.equal(c.posts, 1);
});

test('超过 2 秒会重新解析，能看到外部改绑', async () => {
  const c = fakeClient(['p1', 'p2']);
  assert.equal((await c.projectFor('s1')).id, 'p1');
  await sleep(2100);
  assert.equal((await c.projectFor('s1')).id, 'p2', '缓存没失效，说明 TTL 被前面的立即返回短路了');
  assert.equal(c.posts, 2);
});

test('不同会话互不干扰', async () => {
  const c = new EngineClient({ clientId: 'test' });
  c.post = async (_p, body) => ({ project: { id: 'p-' + (body.sessionId ?? body.session_id) } });
  assert.equal((await c.projectFor('a')).id, 'p-a');
  assert.equal((await c.projectFor('b')).id, 'p-b');
});
