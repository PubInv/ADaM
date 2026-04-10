import { useEffect, useState } from 'react'
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native'
import { connectMqtt, disconnectMqtt, publishAction } from './src/services/mqttService'
import { Alarm } from './src/types/alarm'

export default function App() {
  const [status, setStatus] = useState('Connecting...')
  const [error, setError] = useState('')
  const [currentAlarm, setCurrentAlarm] = useState<Alarm | null>(null)
  const [history, setHistory] = useState<string[]>([])

  useEffect(() => {
    connectMqtt({
      onConnect: () => {
        setStatus('Connected')
        setError('')
        setHistory(prev => [`Connected to broker`, ...prev])
      },
      onDisconnect: () => {
        setStatus('Disconnected')
        setHistory(prev => [`Disconnected from broker`, ...prev])
      },
      onError: (err) => {
        setError(err)
        setHistory(prev => [`Error: ${err}`, ...prev])
      },
      onAlarm: (alarm) => {
        setCurrentAlarm(alarm)
        setHistory(prev => [`Alarm received: ${alarm.message}`, ...prev])
      },
    })

    return () => {
      disconnectMqtt()
    }
  }, [])

  const handleAction = (action: string) => {
    try {
      publishAction(action, currentAlarm ?? undefined)
      setHistory(prev => [`Action sent: ${action}`, ...prev])
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to publish action'
      setError(msg)
      setHistory(prev => [`Error: ${msg}`, ...prev])
    }
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>ADaM Mobile MVP</Text>
        <Text style={styles.status}>Status: {status}</Text>

        {error ? <Text style={styles.error}>Error: {error}</Text> : null}

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Current Alarm</Text>

          {currentAlarm ? (
            <>
              <Text style={styles.label}>Message</Text>
              <Text style={styles.value}>{currentAlarm.message}</Text>

              <Text style={styles.label}>Severity</Text>
              <Text style={styles.value}>{currentAlarm.severity || 'unknown'}</Text>

              <Text style={styles.label}>Timestamp</Text>
              <Text style={styles.value}>{currentAlarm.timestamp || 'n/a'}</Text>
            </>
          ) : (
            <Text style={styles.value}>No alarm received yet</Text>
          )}
        </View>

        <View style={styles.buttonRow}>
          <ActionButton label="Acknowledge" onPress={() => handleAction('acknowledge')} />
          <ActionButton label="Complete" onPress={() => handleAction('complete')} />
        </View>

        <View style={styles.buttonRow}>
          <ActionButton label="Dismiss" onPress={() => handleAction('dismiss')} />
          <ActionButton label="Shelve" onPress={() => handleAction('shelve')} />
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>History</Text>
          {history.length === 0 ? (
            <Text style={styles.value}>No events yet</Text>
          ) : (
            history.slice(0, 10).map((item, index) => (
              <Text key={index} style={styles.historyItem}>
                • {item}
              </Text>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}

function ActionButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.button} onPress={onPress}>
      <Text style={styles.buttonText}>{label}</Text>
    </TouchableOpacity>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  content: {
    padding: 20,
    gap: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#ffffff',
  },
  status: {
    fontSize: 16,
    color: '#d1d5db',
  },
  error: {
    color: '#fca5a5',
    fontSize: 14,
  },
  card: {
    backgroundColor: '#1f2937',
    padding: 16,
    borderRadius: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 12,
  },
  label: {
    fontSize: 13,
    color: '#9ca3af',
    marginTop: 8,
  },
  value: {
    fontSize: 16,
    color: '#f9fafb',
    marginTop: 2,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  button: {
    flex: 1,
    backgroundColor: '#2563eb',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  buttonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  historyItem: {
    color: '#e5e7eb',
    marginTop: 6,
  },
})