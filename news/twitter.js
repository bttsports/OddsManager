import fetch from 'node-fetch';

const LIST_ID = 'your_list_id';
const authToken = process.env.TWITTER_AUTH_TOKEN;   // from auth_token cookie
const ct0 = process.env.TWITTER_CT0;                // from ct0 cookie
const bearer = process.env.TWITTER_BEARER;          // from web client (e.g., starts with "Bearer AAAAAA...")

async function fetchList(cursor = null) {
  const params = new URLSearchParams({
    count: '100',
    withTweetResult: 'true',
    withBirdwatchNotes: 'false',
    withVoice: 'true',
    ...(cursor ? { cursor } : {})
  });

  const res = await fetch(
    `https://twitter.com/i/api/2/list/${LIST_ID}/tweets?${params.toString()}`,
    {
      headers: {
        'authorization': bearer,
        'cookie': `auth_token=${authToken}; ct0=${ct0};`,
        'x-csrf-token': ct0,
        'x-twitter-active-user': 'yes',
        'user-agent': 'Mozilla/5.0',
      }
    }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
