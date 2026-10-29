import {ref} from 'vue'
// Public product discovery selects standalone or explicitly configured shared compatibility views.
export const isWechatProduct = import.meta.env.VITE_PRODUCT === 'wechat'
export const productTitle = isWechatProduct ? '智启图文' : '智启无人'

export const standalone=ref(false)
let productLoaded:Promise<void>|undefined
export function loadProduct(){return productLoaded ||= fetch('/api/v1/product').then(r=>r.ok?r.json():null).then(data=>{standalone.value=data?.data?.mode==='standalone'}).catch(()=>{})}
