import { Vibration } from 'react-native'
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio'

let alarmPlayer: ReturnType<typeof createAudioPlayer> | null = null

export async function loadAlarmSound()
{
    if (alarmPlayer) return

    await setAudioModeAsync({playsInSilentMode: true,})

    alarmPlayer = createAudioPlayer(require('../../assets/medium1.mp3'))

}

export async function triggerAlarmAlert(isMuted: boolean)
{
    try {
        if (isMuted) return

        Vibration.vibrate()

        if (alarmPlayer)
        {
            alarmPlayer.seekTo(0)
            alarmPlayer.play()
        }
    } catch (err)
    {
        console.log('Failed to trigger alarm alert', err)
    }
}

export function stopAlarmAlert()
{
    try {
        Vibration.cancel()

        if(alarmPlayer && alarmPlayer.playing)
        {
            alarmPlayer.pause()
            alarmPlayer.seekTo(0)
        }
    }catch (err)
    {
        console.log('Failed to stop alarm alert:', err)
    }
}

export function cleanupAlarmSound() {
    if (alarmPlayer) {
        alarmPlayer.remove()
        alarmPlayer = null
    }
}