<template>
  <div class="flex h-full flex-col overflow-hidden">
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs routeName="Manager AI" />
      </template>
      <template #right-header>
        <Dropdown
          :options="staleDayOptions"
          :button="{
            label: staleDaysLabel,
            variant: 'outline',
            iconRight: 'chevron-down',
          }"
        />
        <Button
          :label="__('Refresh')"
          iconLeft="refresh-cw"
          :loading="overview.loading"
          @click="refresh"
        />
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto p-5">
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="card in summaryCards"
          :key="card.label"
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4"
        >
          <div class="text-sm font-medium text-ink-gray-6">
            {{ card.label }}
          </div>
          <div class="mt-2 text-3xl font-semibold text-ink-gray-9">
            {{ card.value }}
          </div>
          <div class="mt-2 text-xs text-ink-gray-5">
            {{ card.helper }}
          </div>
        </div>
      </div>

      <div
        v-if="overview.loading && !overview.data"
        class="mt-5 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-4 py-8 text-center text-sm text-ink-gray-5"
      >
        {{ __('Loading manager insights...') }}
      </div>

      <div v-else class="mt-5 grid gap-5 xl:grid-cols-2">
        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('High Risk Suggestions') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Suggestions that need a manager review before execution.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="red"
              :label="String(highRiskSuggestions.length)"
            />
          </div>
          <div v-if="highRiskSuggestions.length" class="divide-y divide-outline-gray-2">
            <div
              v-for="item in highRiskSuggestions"
              :key="item.name"
              class="space-y-2 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink-gray-8">
                    {{ item.title || item.name }}
                  </div>
                  <div class="mt-1 text-xs text-ink-gray-5">
                    {{ __('Channel') }}: {{ item.channel || __('Unknown') }}
                  </div>
                </div>
                <Badge
                  variant="subtle"
                  :theme="statusTheme(item.status)"
                  :label="item.status || __('Open')"
                />
              </div>
              <div class="flex items-center justify-between gap-3 text-xs text-ink-gray-5">
                <router-link
                  v-if="routeForReference(item.reference)"
                  :to="routeForReference(item.reference)"
                  class="truncate font-medium text-ink-gray-7 hover:text-ink-gray-9"
                >
                  {{ referenceLabel(item.reference) }}
                </router-link>
                <span v-else class="truncate">
                  {{ referenceLabel(item.reference) }}
                </span>
                <span :title="formatDate(item.updated_at)">
                  {{ item.updated_at ? timeAgo(item.updated_at) : __('Unknown') }}
                </span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No high risk suggestions at the moment.') }}
          </div>
        </section>

        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Stale Threads') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Threads with no recent touchpoint inside the selected window.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="orange"
              :label="String(staleThreads.length)"
            />
          </div>
          <div v-if="staleThreads.length" class="divide-y divide-outline-gray-2">
            <div
              v-for="thread in staleThreads"
              :key="thread.name"
              class="space-y-2 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink-gray-8">
                    {{ thread.summary || thread.thread_key }}
                  </div>
                  <div class="mt-1 flex items-center gap-2 text-xs text-ink-gray-5">
                    <span>{{ thread.channel || __('Unknown') }}</span>
                    <span>&middot;</span>
                    <span>
                      {{ __('Touchpoints') }}: {{ thread.touchpoint_count || 0 }}
                    </span>
                  </div>
                </div>
                <Badge
                  variant="subtle"
                  :theme="threadStatusTheme(thread.status)"
                  :label="thread.status || __('Active')"
                />
              </div>
              <div class="flex items-center justify-between gap-3 text-xs text-ink-gray-5">
                <router-link
                  v-if="routeForReference(thread.reference)"
                  :to="routeForReference(thread.reference)"
                  class="truncate font-medium text-ink-gray-7 hover:text-ink-gray-9"
                >
                  {{ referenceLabel(thread.reference) }}
                </router-link>
                <span v-else class="truncate">
                  {{ referenceLabel(thread.reference) }}
                </span>
                <span :title="formatDate(thread.last_touchpoint_at)">
                  {{
                    thread.last_touchpoint_at
                      ? timeAgo(thread.last_touchpoint_at)
                      : __('No touchpoint yet')
                  }}
                </span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No stale threads found for this time window.') }}
          </div>
        </section>

        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Sync Alerts') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Recent channel errors emitted by the sync pipeline.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="red"
              :label="String(syncAlerts.length)"
            />
          </div>
          <div v-if="syncAlerts.length" class="divide-y divide-outline-gray-2">
            <div
              v-for="alert in syncAlerts"
              :key="alert.name"
              class="space-y-2 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink-gray-8">
                    {{ alert.message }}
                  </div>
                  <div class="mt-1 text-xs text-ink-gray-5">
                    {{ alert.channel || __('Unknown') }} / {{ alert.code }}
                  </div>
                </div>
                <Badge
                  variant="subtle"
                  :theme="alertSeverityTheme(alert.severity)"
                  :label="alert.severity || __('warning')"
                />
              </div>
              <div class="flex items-center justify-between gap-3 text-xs text-ink-gray-5">
                <span class="truncate">
                  {{
                    alert.context?.cursor_id ||
                    alert.context?.event_id ||
                    __('No cursor attached')
                  }}
                </span>
                <span :title="formatDate(alert.created_at)">
                  {{ alert.created_at ? timeAgo(alert.created_at) : __('Unknown') }}
                </span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No active sync alerts.') }}
          </div>
        </section>

        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Deals Without Next Step') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Recently updated deals that still miss an explicit next action.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="amber"
              :label="String(dealsWithoutNextStep.length)"
            />
          </div>
          <div
            v-if="dealsWithoutNextStep.length"
            class="divide-y divide-outline-gray-2"
          >
            <div
              v-for="deal in dealsWithoutNextStep"
              :key="deal.name"
              class="space-y-2 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <router-link
                    :to="{ name: 'Deal', params: { dealId: deal.name } }"
                    class="truncate text-sm font-medium text-ink-gray-8 hover:text-ink-gray-9"
                  >
                    {{ deal.name }}
                  </router-link>
                  <div class="mt-1 text-xs text-ink-gray-5">
                    {{ __('Owner') }}:
                    {{ deal.deal_owner ? getUser(deal.deal_owner).full_name : __('Unassigned') }}
                  </div>
                </div>
                <Badge
                  variant="subtle"
                  theme="blue"
                  :label="deal.status || __('Unknown')"
                />
              </div>
              <div class="text-xs text-ink-gray-5">
                {{ __('Updated') }}:
                <span :title="formatDate(deal.updated_at)">
                  {{ deal.updated_at ? timeAgo(deal.updated_at) : __('Unknown') }}
                </span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('Every recent deal already has a next step.') }}
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import { usersStore } from '@/stores/users'
import { formatDate, timeAgo } from '@/utils'
import { Badge, Button, Dropdown, createResource, usePageMeta } from 'frappe-ui'
import { computed, ref } from 'vue'

const { getUser } = usersStore()

const staleDays = ref(7)

const overview = createResource({
  url: 'crm.api.manager_ai.get_manager_overview',
  makeParams() {
    return {
      limit: 8,
      stale_days: staleDays.value,
    }
  },
  auto: true,
})

const staleDayOptions = computed(() => [
  {
    label: __('Stale after 3 days'),
    onClick: () => updateStaleDays(3),
  },
  {
    label: __('Stale after 7 days'),
    onClick: () => updateStaleDays(7),
  },
  {
    label: __('Stale after 14 days'),
    onClick: () => updateStaleDays(14),
  },
])

const staleDaysLabel = computed(() =>
  __('Stale after {0} days', [staleDays.value]),
)

const summary = computed(() => overview.data?.summary || {})
const highRiskSuggestions = computed(
  () => overview.data?.high_risk_suggestions || [],
)
const staleThreads = computed(() => overview.data?.stale_threads || [])
const syncAlerts = computed(() => overview.data?.sync_alerts || [])
const dealsWithoutNextStep = computed(
  () => overview.data?.deals_without_next_step || [],
)

const summaryCards = computed(() => [
  {
    label: __('High Risk'),
    value: summary.value.high_risk_suggestion_count || 0,
    helper: __('Suggestions waiting for manager review'),
  },
  {
    label: __('Stale Threads'),
    value: summary.value.stale_thread_count || 0,
    helper: __('Threads inactive for more than {0} days', [staleDays.value]),
  },
  {
    label: __('Sync Alerts'),
    value: summary.value.sync_alert_count || 0,
    helper: __('Errors raised by channel pull or webhook sync'),
  },
  {
    label: __('Missing Next Step'),
    value: summary.value.deals_without_next_step_count || 0,
    helper: __('Deals that still need an explicit follow-up'),
  },
])

function updateStaleDays(days) {
  staleDays.value = days
  refresh()
}

function refresh() {
  overview.reload()
}

function routeForReference(reference) {
  if (!reference?.doctype || !reference?.name) return null

  const mapping = {
    'CRM Deal': {
      name: 'Deal',
      params: { dealId: reference.name },
    },
    'CRM Lead': {
      name: 'Lead',
      params: { leadId: reference.name },
    },
    Contact: {
      name: 'Contact',
      params: { contactId: reference.name },
    },
    'CRM Organization': {
      name: 'Organization',
      params: { organizationId: reference.name },
    },
  }

  return mapping[reference.doctype] || null
}

function referenceLabel(reference) {
  if (!reference?.doctype || !reference?.name) return __('Unlinked record')
  return `${reference.doctype}: ${reference.name}`
}

function statusTheme(status) {
  if (status === 'Closed' || status === 'Approved') return 'green'
  if (status === 'In Progress' || status === 'Drafted') return 'orange'
  return 'red'
}

function threadStatusTheme(status) {
  if (status === 'Closed') return 'gray'
  if (status === 'Archived') return 'orange'
  return 'red'
}

function alertSeverityTheme(severity) {
  if (severity === 'warning') return 'orange'
  if (severity === 'info') return 'blue'
  return 'red'
}

usePageMeta(() => {
  return { title: __('Manager AI') }
})
</script>
