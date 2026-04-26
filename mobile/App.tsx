import { useEffect, useState, useRef } from 'react'
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native'
import { connectMqtt, disconnectMqtt, publishAction } from './src/services/mqttService'
import { Alarm } from './src/types/alarm'
import { loadAlarmSound, triggerAlarmAlert, stopAlarmAlert, cleanupAlarmSound } from './src/services/alertService'

export default function App() {
  const [status, setStatus] = useState('Connecting...')
  const [error, setError] = useState('')
  const [currentAlarm, setCurrentAlarm] = useState<Alarm | null>(null)
  const [history, setHistory] = useState<string[]>([])
  const [isMuted, setIsMuted] = useState(false)
  const [currentPage, setCurrentPage] = useState<'home' | 'logs'>('home')
  const isMutedRef = useRef(false)

  useEffect(() => {
  isMutedRef.current = isMuted
}, [isMuted])

  useEffect(() => {
    loadAlarmSound()
    

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
      onAlarm: async (alarm) => {
        setCurrentAlarm(alarm)
        setHistory(prev => [`Alarm received: ${alarm.message}`, ...prev])

        await triggerAlarmAlert(isMutedRef.current)
      },
      

    })

    return () => {
      disconnectMqtt()
      cleanupAlarmSound()
    }
  }, [])

  const handleAction = (action: string) => {
    try {
      publishAction(action, currentAlarm ?? undefined)
      const alarmLabel = currentAlarm
      ? `[ID: ${currentAlarm.id ?? 'n/a'}] ${currentAlarm.message}`
      : 'No active alarm'

    if (action === 'acknowledge') {
      setHistory(prev => [`Acknowledgment sent for ${alarmLabel}`, ...prev])
    } else {
      setHistory(prev => [`Action sent: ${action} for ${alarmLabel}`, ...prev])
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Failed to publish action'
    setError(msg)
    setHistory(prev => [`Error: ${msg}`, ...prev])
  }
  }

  const toggleMute = () => {
    setIsMuted(prev => {
      const nextMuted = !prev

      if(nextMuted) {
        stopAlarmAlert()
        setHistory(historyPrev => ['Alerts muted', ...historyPrev])
      }else {
        setHistory(historyPrev => ['Alerts unmuted', ...historyPrev])
      }
      return nextMuted
    })
  }

   if(currentPage === 'logs') {
     return (
       <SafeAreaView style={styles.container}>
         <View style={styles.logsHeader}>
           <TouchableOpacity style={styles.smallTopButton} onPress={() => setCurrentPage('home')}>
             <Text style={styles.smallTopButtonText}>Home</Text>
           </TouchableOpacity>
         </View>

         <ScrollView contentContainerStyle={styles.logsContent}>
           <Text style={styles.title}>Logs</Text>

         <View style={styles.card}>
             {history.length === 0 ? (
               <Text style={styles.value}>No logs recorded yet</Text>
             ) : (
               history.map((item, index) => (
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

  return (
    <SafeAreaView style={styles.container}>
    <TouchableOpacity style={styles.muteButton} onPress={toggleMute}>
      <Text style = {styles.muteButtonText}>{isMuted ? 'Unmute' : 'Mute'}</Text>
    </TouchableOpacity>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>ADaM Mobile </Text>
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

      <TouchableOpacity style={styles.logsButton} onPress={() => setCurrentPage('logs')}>
        <Text style={styles.logsButtonText}>All Logs</Text>
      </TouchableOpacity>
    

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
    paddingTop: 70,
    gap: 16,
  },
  logsContent:{
    padding: 20,
    paddingTop: 70,
    gap:16,
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
  muteButton: {
  position: 'absolute',
  top: 46,
  right: 16,
  zIndex: 10,
  minWidth: 90,
  backgroundColor: '#374151',
  paddingVertical: 10,
  paddingHorizontal: 14,
  borderRadius: 10,
  alignItems: 'center',
},
muteButtonText: {
  color: '#ffffff',
  fontWeight: '700',
},
logsButton: {
  position: 'absolute',
  left: 70,
  right: 70,
  bottom: -70,
  zIndex: 10,
  minWidth: 90,
  marginTop: 0,
  backgroundColor: '#374151',
  paddingVertical: 14,
  borderRadius: 10,
  alignItems: 'center',
  marginBottom: 20,
},
logsButtonText: {
  color: '#ffffff',
  fontWeight: '700',
  fontSize: 16,
},
logsHeader: {
  position: 'absolute',
  top: 16,
  left: 16,
  zIndex: 10,
},
smallTopButton: {
  position: 'absolute',
  top: 30,
  left: 270,
  zIndex: 10,
  minWidth: 90,
  backgroundColor: '#374151',
  paddingVertical: 10,
  paddingHorizontal: 14,
  borderRadius: 10,
  alignItems: 'center',
},
smallTopButtonText: {
  color: '#ffffff',
  fontWeight: '700',
},
})


// notes:
// the app doesn't send back acknowledments to the server. (Done)
// no mute/unmute functionality implemented yet. (Done)
// no sounds implemented.(Done)
// a proper log history tab
//