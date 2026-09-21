<template>
  <q-page class="page-pad">
    <div class="row items-center q-mb-md">
      <div class="text-h5">质量门禁</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
    </div>

    <q-card v-if="auth.role === 'bioops'" flat bordered class="q-mb-lg">
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">门禁阈值设置</div>
        <div class="text-caption text-grey-7 q-mb-md">
          阈值保存后立即生效，仅对之后完成的作业判定；已成功的作业重跑后才会按新阈值进入超标列表。
        </div>
        <div class="row q-col-gutter-md items-end">
          <div class="col-12 col-sm-4">
            <div class="text-caption text-grey-7 q-mb-xs">平均质量下限（mean_quality ≥）</div>
            <q-input
              v-model.number="form.min_mean_quality"
              type="number"
              outlined
              dense
              :rules="[(v) => (v !== null && v >= 0 && v <= 93) || '范围 0 ~ 93']"
              hint="作业平均质量低于该值即触发门禁"
            />
          </div>
          <div class="col-12 col-sm-4">
            <div class="text-caption text-grey-7 q-mb-xs">N 率上限（n_rate ≤）</div>
            <q-input
              v-model.number="form.max_n_rate"
              type="number"
              step="0.01"
              outlined
              dense
              :rules="[(v) => (v !== null && v >= 0 && v <= 1) || '范围 0 ~ 1']"
              hint="作业 N 率高于该值即触发门禁"
            />
          </div>
          <div class="col-12 col-sm-4">
            <q-btn color="primary" label="保存门禁" :loading="saving" @click="save" />
          </div>
        </div>
        <div v-if="gate" class="text-caption text-grey-6 q-mt-md">
          最近更新：{{ gate.updated_by }} · {{ formatTime(gate.updated_at) }}
        </div>
      </q-card-section>
    </q-card>

    <div class="text-subtitle1 q-mb-sm">门禁超标列表（仅触发门禁的成功作业）</div>
    <q-table
      flat
      bordered
      row-key="job_id"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      hide-pagination
      :pagination="{ rowsPerPage: 0 }"
    >
      <template #body-cell-metrics="props">
        <q-td :props="props">
          Q={{ props.row.mean_quality ?? '—' }} · N={{ props.row.n_rate ?? '—' }}
        </q-td>
      </template>
      <template #body-cell-violations="props">
        <q-td :props="props">
          <div v-for="v in props.row.violations" :key="v.field" class="q-mb-xs">
            <q-badge color="negative" class="text-wrap">
              {{ v.message }}
            </q-badge>
          </div>
        </q-td>
      </template>
      <template #body-cell-triggered_at="props">
        <q-td :props="props">{{ formatTime(props.row.triggered_at) }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props">
          <q-btn dense flat color="primary" label="作业详情" :to="`/jobs/${props.row.job_id}`" />
        </q-td>
      </template>
      <template #no-data>
        <div class="text-grey-6 q-pa-md">暂无触发门禁的作业</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { getQualityGate, listGateViolations, updateQualityGate } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const loading = ref(false)
const saving = ref(false)
const gate = ref(null)
const rows = ref([])
const form = reactive({ min_mean_quality: null, max_n_rate: null })

const columns = [
  { name: 'job_id', label: '作业 ID', field: 'job_id', align: 'left' },
  { name: 'sample_name', label: '样例', field: 'sample_name', align: 'left' },
  { name: 'created_by', label: '提交人', field: 'created_by', align: 'left' },
  { name: 'metrics', label: '作业指标', field: 'metrics', align: 'left' },
  { name: 'violations', label: '超标字段', field: 'violations', align: 'left' },
  { name: 'triggered_at', label: '触发时间', field: 'triggered_at', align: 'left' },
  { name: 'actions', label: '操作', field: 'actions', align: 'left' },
]

function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function load() {
  loading.value = true
  try {
    const [g, v] = await Promise.all([getQualityGate(), listGateViolations()])
    gate.value = g
    form.min_mean_quality = g.min_mean_quality
    form.max_n_rate = g.max_n_rate
    rows.value = v
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

async function save() {
  if (form.min_mean_quality === null || form.max_n_rate === null) {
    $q.notify({ type: 'warning', message: '请填写两个阈值' })
    return
  }
  saving.value = true
  try {
    const g = await updateQualityGate({
      min_mean_quality: form.min_mean_quality,
      max_n_rate: form.max_n_rate,
    })
    gate.value = g
    $q.notify({ type: 'positive', message: '门禁阈值已保存' })
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '保存失败' })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
