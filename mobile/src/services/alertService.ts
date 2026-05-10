import { Vibration } from 'react-native'
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio'
import * as Speech from 'expo-speech'
import type { Alarm} from '../types/alarm'

//let alarmPlayer: ReturnType<typeof createAudioPlayer> | null = null

let severityPlayer: ReturnType<typeof createAudioPlayer> | null = null
const severitySoundMap = {
  Informational: require('../../assets/Informational.m4a'),
  Problem: require('../../assets/Problem.m4a'),
  Warning: require('../../assets/Warning.m4a'),
  Critical: require('../../assets/Critical.m4a'),
  Panic: require('../../assets/Panic.m4a'),
}

export async function prepareAlertAudio()
{
    console.log('Preparing alert audio mode')

  await setAudioModeAsync({
    playsInSilentMode: true,
  })
    console.log('Audio mode prepared')

}

const getSeverityLabel = (severity?: string): keyof typeof severitySoundMap | null => {
  if (!severity) return null 

  const value = String(severity).trim().toLowerCase()

  if (value === '1' || value === 'informational') return 'Informational'
  if (value === '2' || value === 'problem') return 'Problem'
  if (value === '3' || value === 'warning') return 'Warning'
  if (value === '4' || value === 'critical') return 'Critical'
  if (value === '5' || value === 'panic') return 'Panic'

  return null
}
// const severityLabels: Record<number, string> = {
//     1: 'Informational',
//     2: 'Problem',
//     3: 'Warning',
//     4: 'Critical',
//     5: 'Panic',
// }

// function getSeverityLabel(severity?: string): string {
//   if (!severity) return 'Unknown severity'

//   const trimmed = severity.trim()

//   const numericValue = Number(trimmed)
//   if (!Number.isNaN(numericValue) && severityLabels[numericValue]) {
//     return severityLabels[numericValue]
//   }

//   const normalized = trimmed.toLowerCase()

//   if (normalized === 'informational') return 'Informational'
//   if (normalized === 'problem') return 'Problem'
//   if (normalized === 'warning') return 'Warning'
//   if (normalized === 'critical') return 'Critical'
//   if (normalized === 'panic') return 'Panic'

//   return trimmed
// }

// function buildAlarmSpeechText(alarm: Alarm): string {
//   const severityLabel = getSeverityLabel(alarm.severity)
//   const message = alarm.message?.trim() || 'No message provided'

//   return `${severityLabel}. ${message}.`
// }

export async function triggerAlarmAnnouncement(alarm: Alarm, isMuted: boolean) {
  if (isMuted) return

  try {
    console.log('Alarm received in playSeveritySound:', alarm)
    console.log('Raw severity:', alarm.severity)
    Vibration.vibrate()

    const severityLabel = getSeverityLabel(alarm.severity)
        console.log('Mapped severity label:', severityLabel)

    
    const source = severitySoundMap[severityLabel as keyof typeof severitySoundMap]

    if (!source){
      console.log('no severity sound found for:', alarm.severity)
      return
    }

    if (severityPlayer) {
      severityPlayer.remove()
      severityPlayer = null
    }

    
    console.log('Creating audio player')

    severityPlayer = createAudioPlayer(source)
    console.log('play() was called successfully')

    severityPlayer.play()

    // Speech.stop()
    // Speech.speak(speechText, {
    //   language: 'en',
    //   pitch: 1.0,
    //   rate: 0.95,
    //})
  } catch (err) {
    console.log('Failed to announce alarm:', err)
  }
}

// export function stopAlarmAnnouncement() {
//   Vibration.cancel()
//   Speech.stop()
// }

// export async function loadAlarmSound()
// {
//     if (alarmPlayer) return

//     await setAudioModeAsync({playsInSilentMode: true,})

//     alarmPlayer = createAudioPlayer(require('../../assets/medium1.mp3'))

// }

// export async function triggerAlarmAlert(isMuted: boolean)
// {
//     try {
//         if (isMuted) return

//         Vibration.vibrate()

//         if (alarmPlayer)
//         {
//             alarmPlayer.seekTo(0)
//             alarmPlayer.play()
//         }
//     } catch (err)
//     {
//         console.log('Failed to trigger alarm alert', err)
//     }
// }

export function stopAlarmAlert()
{
    try {
        Vibration.cancel()

        if(severityPlayer)
        {
            severityPlayer.remove()
            severityPlayer = null
        }
    }catch (err)
    {
        console.log('Failed to stop alarm alert:', err)
    }
}

export function cleanupAlarmSound() {
    if (severityPlayer) {
        severityPlayer.remove()
        severityPlayer = null
    }
}