import {mount,flushPromises} from '@vue/test-utils'
import {createPinia,setActivePinia} from 'pinia'
import {beforeEach,describe,it,expect,vi} from 'vitest'
import Accounts from './StandaloneAccounts.vue'
import Selection from './SelectionPipelinePanel.vue'
import {useAuthStore} from '@/stores/auth'
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),put:vi.fn(),delete:vi.fn()}))
vi.mock('@/utils/request',()=>({default:api}))
beforeEach(()=>{
 vi.clearAllMocks();sessionStorage.clear();setActivePinia(createPinia())
 const auth=useAuthStore();auth.role='super_admin';auth.userId='test-user'
 api.get.mockImplementation((path:string)=>Promise.resolve({success:true,data:path==='/wechat-workspace/accounts'?[{accountId:'00000000-0000-4000-8000-000000000001',accountName:'Test account',configured:true,allowPublish:false}]:[]}))
 api.post.mockResolvedValue({success:true,data:{}})
})
describe('standalone workspace',()=>{
 it('creates an account with a valid UUID on LAN HTTP and never displays saved secrets',async()=>{
  const wrapper=mount(Accounts);await flushPromises()
  expect(wrapper.text()).toContain('凭据已配置')
  expect(wrapper.find('input[type=password]').element.getAttribute('value')).toBeNull()
  await wrapper.find('input').setValue('My official account')
  await wrapper.find('form').trigger('submit');await flushPromises()
  expect(api.post).toHaveBeenCalledWith('/wechat-workspace/accounts',expect.objectContaining({requestId:expect.stringMatching(/^[a-f0-9-]{36}$/),accountName:'My official account'}))
  wrapper.unmount()
 })
 it('prevents read-only operators from submitting account changes',async()=>{
  const auth=useAuthStore();auth.role='readonly_operator';auth.permissions=['wechat.read']
  const wrapper=mount(Accounts);await flushPromises()
  expect(wrapper.findAll('button').every(b=>b.attributes('disabled')!==undefined)).toBe(true)
  wrapper.unmount()
 })
 it('reuses the selected news article without selecting a second model call',async()=>{
  const wrapper=mount(Selection,{props:{listings:[],aiConfigured:true,selectedArticleId:'00000000-0000-4000-8000-000000000099'}})
  await flushPromises();expect(wrapper.text()).toContain('不重新调用模型')
  expect(wrapper.text()).not.toContain('写作方式')
  await wrapper.find('form').trigger('submit');await flushPromises()
  expect(api.post).toHaveBeenCalledWith('/research/selection-runs',expect.objectContaining({article_id:'00000000-0000-4000-8000-000000000099',listing_ids:[],query:''}))
  wrapper.unmount()
 })
})
