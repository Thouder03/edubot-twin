<script setup lang="ts">
import { ContentWrap } from '@/components/ContentWrap'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('student-home')
</script>

<template>
  <ContentWrap>
    <div :class="prefixCls">
      <!-- 学生首页内容区域 - 当前为空白 -->
    </div>
  </ContentWrap>
</template>

<style lang="less" scoped>
@prefix-cls: ~'@{adminNamespace}-student-home';

.@{prefix-cls} {
  min-height: 400px;
}
</style>
