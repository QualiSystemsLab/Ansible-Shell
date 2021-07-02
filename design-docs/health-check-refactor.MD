# Health Check Refactor
Entire Driver execution shouldn't fail if health check fails for first machine

## Details
- if health check fails, tag attribute that it failed, continue to next item
	- delay only on first host, then continue to next hosts immediately in loop. No need to cumulatively add delay
- set live status of failed health check in real time
- remove failed health checks from host list of playbook
- merge failed health check items back into output json with other host results

## New ansi_conf attributes needed
- failed_health_check: boolean
    - initialize to false, switch to true on fail
- resource_name: string
  - obtained in driver by doing lookup from IP received in server json with resources on canvas
    

