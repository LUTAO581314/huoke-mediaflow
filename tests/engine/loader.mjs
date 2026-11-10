// 把 store.mjs 里对 ../../engine/dist/*.js 的引用重定向到 stubs/，让 CI 不必编译引擎
import { register } from 'node:module';
register(new URL('./resolve-stub.mjs', import.meta.url));
