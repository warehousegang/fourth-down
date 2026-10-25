import { dispatch, CRON } from './dispatch.mjs';

export default {
  async scheduled(controller, env) {
    controller.noRetry();
    if (controller.cron !== CRON) throw new Error('Unexpected cron expression');
    const result = await dispatch(env, controller.scheduledTime);
    // Only allowlisted receipt fields; never environment, headers or response text.
    console.log(JSON.stringify({ scheduled_at: new Date(controller.scheduledTime).toISOString(), ...result }));
  },
};
