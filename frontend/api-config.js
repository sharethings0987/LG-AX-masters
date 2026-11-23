// 내 컴퓨터(localhost·127.0.0.1)에서 열면 로컬 백엔드(포트 8000)를, 그 외에는 Render 서버를 사용한다.
window.AL_API_BASE_URL = ['localhost', '127.0.0.1'].includes(location.hostname)
  ? (location.port === '8000' ? '' : 'http://127.0.0.1:8000')
  : 'https://lg-ax-masters-api.onrender.com';
