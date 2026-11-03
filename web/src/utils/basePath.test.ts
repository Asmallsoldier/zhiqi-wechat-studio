import {describe,it,expect} from 'vitest'
import {normalizeBase} from './basePath'
describe('deployment base path',()=>{
 it.each(['/','/wechat/','/tools/wechat/'])('accepts same-origin base %s',base=>expect(normalizeBase(base)).toBe(base))
 it.each(['//evil.example/','/../','https://example.com/','/wechat?x/'])('rejects unsafe base %s',base=>expect(()=>normalizeBase(base)).toThrow())
})
