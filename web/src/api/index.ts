import request from '@/utils/request'
export const login = (data: {username:string;password:string}) => request.post('/auth/login',data)
export const logout = () => request.post('/auth/logout')
export const changePassword = (data:{currentPassword:string;newPassword:string}) => request.post('/auth/change-password',data)
