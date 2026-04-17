<template>
  <div class="flex h-full flex-col overflow-hidden">
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs routeName="Channel Ops" />
      </template>
      <template #right-header>
        <Button
          :label="__('Refresh')"
          iconLeft="refresh-cw"
          :loading="isRefreshing"
          @click="refreshAll"
        />
        <Button
          variant="solid"
          :label="__('Pull All')"
          iconLeft="download-cloud"
          :loading="pullAllLoading"
          @click="runPullSyncAll"
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

      <section class="mt-5 rounded-lg border border-outline-gray-2 bg-surface-white">
        <div
          class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
        >
          <div>
            <h2 class="text-base font-semibold text-ink-gray-9">
              {{ __('Credentials') }}
            </h2>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{ __('Masked connector credentials that can be used for manual pull sync.') }}
            </p>
          </div>
          <Badge
            variant="subtle"
            theme="blue"
            :label="String(credentialsList.length)"
          />
        </div>

        <div
          v-if="credentials.loading && !credentials.data"
          class="px-4 py-8 text-center text-sm text-ink-gray-5"
        >
          {{ __('Loading channel credentials...') }}
        </div>

        <div v-else-if="credentialsList.length" class="overflow-x-auto">
          <div class="min-w-[920px]">
            <div class="grid grid-cols-[1.3fr_0.8fr_1fr_0.9fr_1fr_0.8fr_1fr_1fr_auto] gap-3 border-b border-outline-gray-2 px-4 py-3 text-xs font-medium uppercase tracking-wide text-ink-gray-5">
              <div>{{ __('Credential') }}</div>
              <div>{{ __('Channel') }}</div>
              <div>{{ __('Workspace') }}</div>
              <div>{{ __('Auth Type') }}</div>
              <div>{{ __('Base URL') }}</div>
              <div>{{ __('Status') }}</div>
              <div>{{ __('Validated') }}</div>
              <div>{{ __('Expires') }}</div>
              <div>{{ __('Actions') }}</div>
            </div>

            <div
              v-for="credential in credentialsList"
              :key="credential.name"
              class="grid grid-cols-[1.3fr_0.8fr_1fr_0.9fr_1fr_0.8fr_1fr_1fr_auto] gap-3 border-b border-outline-gray-2 px-4 py-3 text-sm text-ink-gray-7 last:border-b-0"
            >
              <div class="min-w-0">
                <div class="truncate font-medium text-ink-gray-8">
                  {{ credential.credential_key || credential.name }}
                </div>
                <div class="mt-1 truncate text-xs text-ink-gray-5">
                  {{ credential.access_token || __('No token stored') }}
                </div>
              </div>
              <div class="truncate">{{ credential.channel || __('Unknown') }}</div>
              <div class="min-w-0">
                <div class="truncate">
                  {{ workspaceLabel(credential.workspace) }}
                </div>
                <div v-if="credential.has_refresh_token" class="mt-1 text-xs text-ink-gray-5">
                  {{ __('Refresh token available') }}
                </div>
              </div>
              <div class="truncate">{{ credential.auth_type || __('Unknown') }}</div>
              <div class="truncate text-xs text-ink-gray-5">
                {{ credential.base_url || __('Default connector endpoint') }}
              </div>
              <div>
                <Badge
                  variant="subtle"
                  :theme="credentialStatusTheme(credential.status)"
                  :label="credential.status || __('Unknown')"
                />
              </div>
              <div class="text-xs text-ink-gray-5">
                <div v-if="credential.last_validated_at">
                  {{ timeAgo(credential.last_validated_at) }}
                </div>
                <div v-else>{{ __('Never') }}</div>
                <div v-if="credential.failure_count" class="mt-1 text-ink-red-3">
                  {{ __('Failures') }}: {{ credential.failure_count }}
                </div>
              </div>
              <div class="text-xs text-ink-gray-5">
                {{
                  credential.expires_at
                    ? formatDate(credential.expires_at)
                    : __('No expiry')
                }}
              </div>
              <div class="flex justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  :label="__('Pull Sync')"
                  iconLeft="download"
                  :loading="activeCredentialId === credential.name"
                  @click="runPullSync(credential)"
                />
              </div>
            </div>
          </div>
        </div>

        <div
          v-else
          class="px-4 py-8 text-center text-sm text-ink-gray-5"
        >
          {{ __('No channel credentials configured yet.') }}
        </div>
      </section>

      <div class="mt-5 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Sync Status') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Latest cursor checkpoints and retry state across channels.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="orange"
              :label="String(syncCursorList.length)"
            />
          </div>

          <div
            v-if="syncCursors.loading && !syncCursors.data"
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('Loading sync cursors...') }}
          </div>

          <div v-else-if="syncCursorList.length" class="divide-y divide-outline-gray-2">
            <div
              v-for="cursor in syncCursorList"
              :key="cursor.name"
              class="space-y-2 px-4 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink-gray-8">
                    {{ cursor.channel || __('Unknown') }} / {{ cursor.cursor_key }}
                  </div>
                  <div class="mt-1 text-xs text-ink-gray-5">
                    {{ workspaceLabel(cursor.workspace) }}
                  </div>
                </div>
                <Badge
                  variant="subtle"
                  :theme="cursorStatusTheme(cursor.status)"
                  :label="cursor.status || __('Unknown')"
                />
              </div>
              <div class="grid gap-2 text-xs text-ink-gray-5 sm:grid-cols-3">
                <div>
                  <div class="font-medium text-ink-gray-6">{{ __('Last Sync') }}</div>
                  <div>
                    {{
                      cursor.last_synced_at
                        ? timeAgo(cursor.last_synced_at)
                        : __('Never')
                    }}
                  </div>
                </div>
                <div>
                  <div class="font-medium text-ink-gray-6">{{ __('Retry Count') }}</div>
                  <div>{{ cursor.retry_count || 0 }}</div>
                </div>
                <div>
                  <div class="font-medium text-ink-gray-6">{{ __('Cursor Value') }}</div>
                  <div class="truncate">
                    {{ cursor.cursor_value || __('Not stored') }}
                  </div>
                </div>
              </div>
              <div
                v-if="cursor.last_error"
                class="rounded-md bg-surface-red-2 px-3 py-2 text-xs text-ink-red-3"
              >
                {{ cursor.last_error }}
              </div>
            </div>
          </div>

          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No sync cursor state recorded yet.') }}
          </div>
        </section>

        <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
          <div
            class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3"
          >
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Recent Alerts') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Operational errors and warnings emitted by channel sync jobs.') }}
              </p>
            </div>
            <Badge
              variant="subtle"
              theme="red"
              :label="String(syncAlertList.length)"
            />
          </div>

          <div
            v-if="syncAlerts.loading && !syncAlerts.data"
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('Loading alerts...') }}
          </div>

          <div v-else-if="syncAlertList.length" class="divide-y divide-outline-gray-2">
            <div
              v-for="alert in syncAlertList"
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
              <div class="text-xs text-ink-gray-5">
                {{
                  alert.context?.cursor_id ||
                  alert.context?.event_id ||
                  __('No additional context')
                }}
              </div>
              <div class="text-xs text-ink-gray-5">
                {{ alert.created_at ? formatDate(alert.created_at) : __('Unknown') }}
              </div>
            </div>
          </div>

          <div
            v-else
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No recent sync alerts.') }}
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import { formatDate, timeAgo } from '@/utils'
import {
  Badge,
  Button,
  call,
  createResource,
  toast,
  usePageMeta,
} from 'frappe-ui'
import { computed, ref } from 'vue'

const activeCredentialId = ref('')
const pullAllLoading = ref(false)

const workspaces = createResource({
  url: 'crm.api.channel_sync.list_channel_workspaces',
  makeParams() {
    return { limit: 50 }
  },
  auto: true,
})

const credentials = createResource({
  url: 'crm.api.channel_sync.list_channel_credentials',
  makeParams() {
    return { limit: 50 }
  },
  auto: true,
})

const syncCursors = createResource({
  url: 'crm.api.channel_sync.list_sync_cursors',
  makeParams() {
    return { limit: 20 }
  },
  auto: true,
})

const syncAlerts = createResource({
  url: 'crm.api.channel_sync.list_sync_alerts',
  makeParams() {
    return { limit: 20 }
  },
  auto: true,
})

const workspaceMap = computed(() => {
  const map = {}
  for (const workspace of workspaces.data?.items || []) {
    map[workspace.name] = workspace
  }
  return map
})

const credentialsList = computed(() => credentials.data?.items || [])
const syncCursorList = computed(() => syncCursors.data?.items || [])
const syncAlertList = computed(() => syncAlerts.data?.items || [])

const isRefreshing = computed(
  () =>
    workspaces.loading ||
    credentials.loading ||
    syncCursors.loading ||
    syncAlerts.loading,
)

const summaryCards = computed(() => {
  const activeCredentials = credentialsList.value.filter(
    (item) => item.status === 'Active',
  ).length
  const failedCursors = syncCursorList.value.filter(
    (item) => item.status === 'Failed',
  ).length
  const errorAlerts = syncAlertList.value.filter(
    (item) => item.severity === 'error',
  ).length

  return [
    {
      label: __('Credentials'),
      value: credentialsList.value.length,
      helper: __('Configured channel connector credentials'),
    },
    {
      label: __('Active'),
      value: activeCredentials,
      helper: __('Credentials currently marked healthy'),
    },
    {
      label: __('Failed Cursors'),
      value: failedCursors,
      helper: __('Sync positions that need retry or manual inspection'),
    },
    {
      label: __('Error Alerts'),
      value: errorAlerts,
      helper: __('Recent operational alerts emitted by sync jobs'),
    },
  ]
})

async function refreshAll() {
  await Promise.all([
    workspaces.reload(),
    credentials.reload(),
    syncCursors.reload(),
    syncAlerts.reload(),
  ])
}

async function runPullSync(credential) {
  activeCredentialId.value = credential.name
  try {
    await call('crm.api.channel_sync.run_pull_sync', {
      channel: credential.channel,
      credential_id: credential.name,
      limit: 20,
      max_retries: 1,
    })
    toast.success(__('Pull sync started'))
    await refreshAll()
  } catch (error) {
    toast.error(error?.messages?.[0] || __('Failed to run pull sync'))
  } finally {
    activeCredentialId.value = ''
  }
}

async function runPullSyncAll() {
  pullAllLoading.value = true
  try {
    await call('crm.api.channel_sync.run_pull_sync_all', {
      limit: 20,
      max_retries: 1,
    })
    toast.success(__('Pull sync started for all channels'))
    await refreshAll()
  } catch (error) {
    toast.error(error?.messages?.[0] || __('Failed to run pull sync for all channels'))
  } finally {
    pullAllLoading.value = false
  }
}

function workspaceLabel(workspaceId) {
  if (!workspaceId) return __('No workspace linked')
  const workspace = workspaceMap.value[workspaceId]
  return workspace?.workspace_name || workspaceId
}

function credentialStatusTheme(status) {
  if (status === 'Expired' || status === 'Invalid') return 'red'
  if (status === 'Pending') return 'orange'
  return 'green'
}

function cursorStatusTheme(status) {
  if (status === 'Failed') return 'red'
  if (status === 'Queued') return 'orange'
  return 'green'
}

function alertSeverityTheme(severity) {
  if (severity === 'warning') return 'orange'
  if (severity === 'info') return 'blue'
  return 'red'
}

usePageMeta(() => {
  return { title: __('Channel Ops') }
})
</script>
