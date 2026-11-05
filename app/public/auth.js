import { connectMicroAuth, supportsMicroAuth } from '/vendor/notify/browser.mjs';

/** Establish a project-specific, HttpOnly browser session using official microAuth. */
export async function connect(project) {
  if (typeof project !== 'string' || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(project)) {
    throw new Error('This project link is invalid.');
  }
  if (!supportsMicroAuth()) {
    throw new Error('Open this workspace in an updated Notify app on your phone to sign in.');
  }
  try {
    const config = await fetch(`/api/projects/${project}/config`, {
      credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    });
    if (!config.ok || !(await config.json()).appId) throw new Error('unregistered');
    const result = await connectMicroAuth({
      challengePath: `/auth/${project}/challenge`,
      sessionPath: `/auth/${project}/session`,
      fields: [],
    });
    if (!result.available) throw new Error('unavailable');
    const session = await fetch(`/auth/${project}/session`, {
      credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    });
    if (!session.ok) throw new Error('session');
    return { authenticated: true, project };
  } catch {
    throw new Error('Sign-in was not completed. Check this project is registered and try again in Notify.');
  }
}
