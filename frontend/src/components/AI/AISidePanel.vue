<template>
  <div class="border-b px-5 py-4">
    <div class="mb-3 flex items-center justify-between gap-2">
      <div class="truncate text-base font-semibold text-ink-gray-9">
        {{ __('AI Copilot') }}
      </div>
      <div class="flex items-center gap-1">
        <Button
          :label="showEvidenceDetails ? __('Hide Evidence') : __('View Evidence')"
          size="sm"
          variant="ghost"
          @click="toggleEvidenceDetails"
        />
        <Button
          :label="__('Approve')"
          size="sm"
          variant="subtle"
          :disabled="!approvableSuggestionId"
          :loading="isApproving"
          @click="approveLatestSuggestion"
        />
        <Button
          :label="__('Generate')"
          size="sm"
          variant="solid"
          :loading="generateSuggestion.loading"
          @click="generate"
        />
      </div>
    </div>

    <div
      v-if="panelContext.loading || suggestions.loading"
      class="text-sm text-ink-gray-5"
    >
      {{ __('Loading AI insights...') }}
    </div>

    <div v-else class="space-y-3">
      <div
        v-if="latestSummary"
        class="rounded-md border border-outline-gray-2 bg-surface-gray-1 p-3"
      >
        <div class="mb-1 text-xs font-medium text-ink-gray-6">
          {{ __('Latest Context') }}
        </div>
        <div class="text-sm text-ink-gray-8">
          {{ latestSummary }}
        </div>
      </div>

      <div class="rounded-md border border-outline-gray-2 bg-surface-gray-1 p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <div class="text-xs font-medium text-ink-gray-6">
            {{ __('Customer Memory') }}
          </div>
          <Button
            :label="__('Refresh Memory')"
            size="sm"
            variant="ghost"
            :loading="compileCustomerMemory.loading"
            @click="compileMemory"
          />
        </div>

        <div
          v-if="customerMemory.loading && !customerMemory.data"
          class="text-xs text-ink-gray-5"
        >
          {{ __('Loading customer memory...') }}
        </div>

        <div v-else-if="customerMemorySummary" class="space-y-3">
          <div class="text-sm text-ink-gray-8">
            {{ customerMemorySummary }}
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs text-ink-gray-6">
            <div class="rounded-md border border-outline-gray-2 p-2">
              <div class="font-medium text-ink-gray-7">{{ __('Sources') }}</div>
              <div class="mt-1 text-lg font-semibold text-ink-gray-9">
                {{ customerMemorySourceCount }}
              </div>
            </div>
            <div class="rounded-md border border-outline-gray-2 p-2">
              <div class="font-medium text-ink-gray-7">
                {{ __('Open Suggestions') }}
              </div>
              <div class="mt-1 text-lg font-semibold text-ink-gray-9">
                {{ customerMemorySignals.open_suggestion_count || 0 }}
              </div>
            </div>
            <div class="rounded-md border border-outline-gray-2 p-2">
              <div class="font-medium text-ink-gray-7">{{ __('Touchpoints') }}</div>
              <div class="mt-1 text-lg font-semibold text-ink-gray-9">
                {{ customerMemorySignals.touchpoint_count || 0 }}
              </div>
            </div>
            <div class="rounded-md border border-outline-gray-2 p-2">
              <div class="font-medium text-ink-gray-7">
                {{ __('Evidence Links') }}
              </div>
              <div class="mt-1 text-lg font-semibold text-ink-gray-9">
                {{ customerMemorySignals.evidence_count || 0 }}
              </div>
            </div>
          </div>
        </div>

        <div
          v-else
          class="rounded-md border border-dashed border-outline-gray-2 p-2 text-xs text-ink-gray-5"
        >
          {{ __('No customer memory compiled yet. Refresh Memory to build one.') }}
        </div>
      </div>

      <div>
        <div class="mb-1 text-xs font-medium text-ink-gray-6">
          {{ __('Suggestions') }} ({{ suggestionItems.length }})
        </div>
        <div
          v-if="!suggestionItems.length"
          class="rounded-md border border-dashed border-outline-gray-2 p-2 text-xs text-ink-gray-5"
        >
          {{ __('No suggestions yet. Click Generate to draft the next actions.') }}
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="item in suggestionItems"
            :key="item.name"
            class="rounded-md border border-outline-gray-2 p-2"
          >
            <div class="truncate text-sm font-medium text-ink-gray-8">
              {{ item.title }}
            </div>
            <div class="mt-1 line-clamp-2 text-xs text-ink-gray-6">
              {{ item.content }}
            </div>
            <div class="mt-1 text-xs text-ink-gray-5">
              {{ __('Risk') }}: {{ __(item.risk_level || 'Medium') }}
            </div>
            <div class="mt-1 text-xs text-ink-gray-5">
              {{ __('Status') }}: {{ __(item.status || 'Open') }}
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2 text-xs text-ink-gray-6">
        <div class="rounded-md border border-outline-gray-2 p-2">
          <div class="font-medium text-ink-gray-7">{{ __('Evidence') }}</div>
          <div class="mt-1 text-lg font-semibold text-ink-gray-9">
            {{ evidenceCount }}
          </div>
        </div>
        <div class="rounded-md border border-outline-gray-2 p-2">
          <div class="font-medium text-ink-gray-7">{{ __('Audit Logs') }}</div>
          <div class="mt-1 text-lg font-semibold text-ink-gray-9">
            {{ auditCount }}
          </div>
        </div>
      </div>

      <div
        v-if="showEvidenceDetails"
        class="space-y-3 rounded-md border border-outline-gray-2 bg-surface-gray-1 p-3"
      >
        <div>
          <div class="mb-1 text-xs font-medium text-ink-gray-6">
            {{ __('Evidence Details') }} ({{ evidenceItems.length }})
          </div>
          <div
            v-if="!evidenceItems.length"
            class="rounded-md border border-dashed border-outline-gray-2 p-2 text-xs text-ink-gray-5"
          >
            {{ __('No evidence details available yet.') }}
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="item in evidenceItems"
              :key="item.name"
              class="rounded-md border border-outline-gray-2 p-2"
            >
              <div class="text-sm font-medium text-ink-gray-8">
                {{ item.title || __('Evidence') }}
              </div>
              <div class="mt-1 line-clamp-2 text-xs text-ink-gray-6">
                {{ item.summary || __('No summary') }}
              </div>
              <div class="mt-1 text-xs text-ink-gray-5">
                {{ __('Source') }}: {{ item.source_type || __('unknown') }}
              </div>
            </div>
          </div>
        </div>

        <div>
          <div class="mb-1 text-xs font-medium text-ink-gray-6">
            {{ __('Approval Audit') }} ({{ auditItems.length }})
          </div>
          <div
            v-if="!auditItems.length"
            class="rounded-md border border-dashed border-outline-gray-2 p-2 text-xs text-ink-gray-5"
          >
            {{ __('No audit logs available yet.') }}
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="item in auditItems"
              :key="item.name"
              class="rounded-md border border-outline-gray-2 p-2"
            >
              <div class="text-sm font-medium text-ink-gray-8">
                {{ __(item.action || 'audit') }}
              </div>
              <div class="mt-1 text-xs text-ink-gray-6">
                {{ __('Status') }}: {{ __(item.status || 'Queued') }}
              </div>
              <div class="mt-1 line-clamp-2 text-xs text-ink-gray-5">
                {{ item.message || __('No details') }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button, call, createResource, toast } from 'frappe-ui'

const props = defineProps({
  referenceDoctype: { type: String, required: true },
  referenceName: { type: String, required: true },
  contextType: { type: String, default: 'deal_panel' },
  channel: { type: String, default: '' },
})

const panelContext = createResource({
  url: 'crm.api.ai.get_panel_context',
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      context_type: props.contextType,
    }
  },
  auto: true,
})

const suggestions = createResource({
  url: 'crm.api.ai.list_suggestions',
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      limit: 5,
    }
  },
  auto: true,
})

const evidenceLinks = createResource({
  url: 'crm.api.ai.list_evidence_links',
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      limit: 20,
    }
  },
  auto: true,
})

const auditLogs = createResource({
  url: 'crm.api.ai.list_audit_logs',
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      limit: 20,
    }
  },
  auto: true,
})

const customerMemory = createResource({
  url: 'crm.api.ai.get_customer_memory',
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
    }
  },
  auto: true,
})

const generateSuggestion = createResource({
  url: 'crm.api.ai.generate_suggestions',
  auto: false,
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      context_type: props.contextType,
      channel: props.channel || null,
    }
  },
  onSuccess() {
    toast.success(__('AI suggestions generated'))
    refresh()
  },
  onError(error) {
    toast.error(error?.messages?.[0] || __('Failed to generate AI suggestions'))
  },
})

const compileCustomerMemory = createResource({
  url: 'crm.api.ai.compile_customer_memory',
  auto: false,
  makeParams() {
    return {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
    }
  },
  onSuccess() {
    toast.success(__('Customer memory refreshed'))
    customerMemory.reload()
  },
  onError(error) {
    toast.error(error?.messages?.[0] || __('Failed to refresh customer memory'))
  },
})

const suggestionItems = computed(() => suggestions.data?.items || [])
const evidenceItems = computed(() => evidenceLinks.data?.items || [])
const auditItems = computed(() => auditLogs.data?.items || [])
const evidenceCount = computed(() => evidenceLinks.data?.total_count || 0)
const auditCount = computed(() => auditLogs.data?.total_count || 0)
const customerMemorySummary = computed(() => customerMemory.data?.summary || '')
const customerMemorySignals = computed(() => customerMemory.data?.signals || {})
const customerMemorySourceCount = computed(
  () => customerMemory.data?.source_count || 0,
)
const latestSummary = computed(() => {
  const sections = panelContext.data?.sections || []
  for (const section of sections) {
    const firstItem = section?.items?.[0]
    if (firstItem?.value) return firstItem.value
    if (firstItem?.summary) return firstItem.summary
  }
  return ''
})
const showEvidenceDetails = ref(false)
const isApproving = ref(false)
const approvableSuggestionId = computed(() => {
  const next = suggestionItems.value.find((item) => item?.status === 'Open')
  return next?.name || ''
})

async function refresh() {
  await Promise.all([
    panelContext.reload(),
    suggestions.reload(),
    evidenceLinks.reload(),
    auditLogs.reload(),
    customerMemory.reload(),
  ])
}

async function approveLatestSuggestion() {
  if (!approvableSuggestionId.value || isApproving.value) return

  isApproving.value = true
  try {
    await call('crm.api.ai.approve_suggestion', {
      suggestion_id: approvableSuggestionId.value,
      decision: 'Accepted',
    })
    toast.success(__('Suggestion approved'))
    await refresh()
  } catch (error) {
    toast.error(error?.messages?.[0] || __('Failed to approve suggestion'))
  } finally {
    isApproving.value = false
  }
}

function generate() {
  generateSuggestion.submit()
}

function compileMemory() {
  compileCustomerMemory.submit()
}

function toggleEvidenceDetails() {
  showEvidenceDetails.value = !showEvidenceDetails.value
  if (showEvidenceDetails.value) {
    evidenceLinks.reload()
    auditLogs.reload()
  }
}
</script>
