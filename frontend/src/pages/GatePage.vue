<template>
  <q-page class="page-pad">
    <div class="row items-center q-mb-md">
      <div class="text-h5">质量门禁</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="loadAll" :loading="loading" />
    </div>

    <!-- Threshold settings: ops edits, auditor reads -->
    <q-card flat bordered class="q-mb-lg">
      <q-card-section>
        <div class="text-subtitle1">门禁阈值</div>
        <div class="text-caption text-grey-7 q-mt-xs">
          成功完成的质控作业，平均质量分低于下限或 N 率高于上限即触发门禁，进入下方超标列表。
          阈值变更对之后重跑的作业生效，作业会留存判定时的阈值快照。
        </div>
      </q-card-section>

      <q-card-section v-if="auth.role === 'bioops'">
        <div class="row q-col-gutter-md items-end">
          <div class="col-12 col-sm-4">
            <q-input
                v-model.number="form.mean_quality_min"
                label="平均质量下限（mean_quality ≥）"
                type="number"
                outlined
                dense
                :min="0"
                :max="93"
                step="0.5"
                hide-bottom-space />
          </div>
          <div class="col-12 col-sm-4">
            <q-input
                v-model.number="form.n_rate_max"
                label="N 率上限（n_rate ≤）"
                type="number"
                outlined
                dense
                :min="0"
                :max="1"
                step="0.01"
                hide-bottom-space />
          </div>
          <div class="col-12 col-sm-4">
            <q-btn
                color="primary"
                label="保存阈值"
                icon="save"
                :loading="saving"
                :disable="!formValid"
                @click="saveSettings" />
          </div>
        </div>
        <div v-if="settings" class="text-caption text-grey-6 q-mt-md">
          当前已生效：平均质量下限 {{ settings.mean_quality_min }} · N 率上限 {{ settings.n_rate_max }}
          · 最近由 {{ settings.updated_by }} 于 {{ formatTime(settings.updated_at) }} 修改
        </div>
      </q-card-section>

      <q-card-section v-else>
        <div class="row q-col-gutter-md items-center">
          <div class="col-12 col-sm-4">
            <div class="text-caption text-grey-7">平均质量下限</div>
            <div class="text-h6">{{ settings?.mean_quality_min ?? '—' }}</div>
          </div>
          <div class="col-12 col-sm-4">
            <div class="text-caption text-grey-7">N 率上限</div>
            <div class="text-h6">{{ settings?.n_rate_max ?? '—' }}</div>
          </div>
        </div>
        <q-banner dense rounded class="bg-grey-2 q-mt-sm text-caption">
          审计员账号仅可查看门禁阈值与超标列表，修改阈值请使用生物运维账号。
        </q-banner>
      </q-card-section>
    </q-card>

    <!-- Dedicated gate-violation list: successful jobs that tripped the gate -->
    <div class="text-subtitle1 q-mb-sm">超标作业列表</div>
    <q-table
        flat
        bordered
        row-key="job_id"
        :rows="rows"
        :columns="columns"
        :loading="loading"
        hide-pagination
        :pagination="{ rowsPerPage: 0 }">
      <template #body-cell-job_id="props">
        <q-td :props="props">
          <q-btn dense flat color="primary" :label="`#${props.row.job_id}`" :to="`/jobs/${props.row.job_id}`" />
        </q-td>
      </template>
      <template #body-cell-mean_quality="props">
        <q-td :props="props">
          <span :class="violated(props.row, 'mean_quality') ? 'text-negative text-weight-bold' : ''">
            {{ props.row.mean_quality ?? '—' }}
          </span>
        </q-td>
      </template>
      <template #body-cell-n_rate="props">
        <q-td :props="props">
          <span :class="violated(props.row, 'n_rate') ? 'text-negative text-weight-bold' : ''">
            {{ props.row.n_rate ?? '—' }}
          </span>
        </q-td>
      </template>
      <template #body-cell-violations="props">
        <q-td :props="props">
          <q-chip
              v-for="v in props.row.violations"
              :key="v.field"
              dense
              square
              color="negative"
              text-color="white"
              :icon="v.field === 'mean_quality' ? 'trending_down' : 'percent'"
              :label="v.message" />
        </q-td>
      </template>
      <template #body-cell-thresholds="props">
        <q-td :props="props" class="text-caption text-grey-7">
          Q≥{{ props.row.thresholds.mean_quality_min ?? '—' }}
          · N≤{{ props.row.thresholds.n_rate_max ?? '—' }}
        </q-td>
      </template>
      <template #body-cell-created_at="props">
        <q-td :props="props">{{ formatTime(props.row.created_at) }}</q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { getGateSettings, listGateViolations, updateGateSettings } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const loading = ref(false)
const saving = ref(false)
const settings = ref(null)
const rows = ref([])
const form = ref({ mean_quality_min: null, n_rate_max: null })

const columns = [
  { name: 'job_id', label: '作业', field: 'job_id', align: 'left' },
  { name: 'sample_name', label: '样例', field: 'sample_name', align: 'left' },
  { name: 'mean_quality', label: '平均质量分', field: 'mean_quality', align: 'left' },
  { name: 'n_rate', label: 'N 率', field: 'n_rate', align: 'left' },
  { name: 'violations', label: '超标字段', field: 'violations', align: 'left' },
  { name: 'thresholds', label: '判定时阈值', field: 'thresholds', align: 'left' },
  { name: 'created_by', label: '提交人', field: 'created_by', align: 'left' },
  { name: 'created_at', label: '完成时间', field: 'created_at', align: 'left' },
]

const formValid = computed(() => {
  const mq = Number(form.value.mean_quality_min)
  const nr = Number(form.value.n_rate_max)
  return Number.isFinite(mq) && mq >= 0 && mq <= 93
      && Number.isFinite(nr) && nr >= 0 && nr <= 1
})

function violated(row, field) {
  return (row.violations || []).some((v) => v.field === field)
}

function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString() : ''
}

async function loadAll() {
  loading.value = true
  try {
    const [s, v] = await Promise.all([getGateSettings(), listGateViolations()])
    settings.value = s
    form.value = {
      mean_quality_min: s.mean_quality_min,
      n_rate_max: s.n_rate_max,
    }
    rows.value = v
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (!formValid.value) {
    $q.notify({ type: 'warning', message: '请检查阈值输入（平均质量 0~93，N 率 0~1）' })
    return
  }
  saving.value = true
  try {
    const s = await updateGateSettings({
      mean_quality_min: Number(form.value.mean_quality_min),
      n_rate_max: Number(form.value.n_rate_max),
    })
    settings.value = s
    form.value = { mean_quality_min: s.mean_quality_min, n_rate_max: s.n_rate_max }
    $q.notify({ type: 'positive', message: '门禁阈值已保存，对之后重跑的作业生效' })
    const v = await listGateViolations()
    rows.value = v
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '保存失败' })
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>
