<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
body {
  margin: 0;
  padding: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
}

/* Keep feedback overlays inside the visible viewport on long admin pages. */
.el-message,
.el-message-box__wrapper {
  position: fixed !important;
  z-index: 4000 !important;
}
.el-message { top: max(16px, env(safe-area-inset-top)) !important; }

@media (max-width: 760px) {
  .admin-layout .el-card__header { padding: 12px 14px; }
  .admin-layout .el-card__body { padding: 14px; }
  .admin-layout .el-form-item { margin-bottom: 14px; }
  .admin-layout .el-form-item__content { min-width: 0; }
  .admin-layout .el-input,
  .admin-layout .el-select,
  .admin-layout .el-date-editor,
  .admin-layout .el-cascader { max-width: 100%; }
  .admin-layout .el-table { width: 100%; }
  .admin-layout .el-table th,
  .admin-layout .el-table td { padding: 7px 0; }
  .admin-layout .el-table .cell { white-space: normal; word-break: break-word; }
  .admin-layout .el-dialog { width: calc(100vw - 24px) !important; max-width: 640px; margin: 12px auto !important; }
  .admin-layout .el-dialog__body { max-height: calc(100dvh - 150px); overflow: auto; padding: 14px; }
  .admin-layout .el-dialog__header { padding: 16px 14px 8px; }
  .admin-layout .el-dialog__footer { padding: 8px 14px 14px; }
  .admin-layout .el-dialog__footer .el-button { margin: 4px 4px 0 0; }
  .admin-layout .el-button + .el-button { margin-left: 6px; }
  .admin-layout .el-pagination { flex-wrap: wrap; justify-content: center; gap: 8px 0; }
}
</style>
