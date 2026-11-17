<?php
declare(strict_types=1);
$configPath = '__PRIVATE_CONFIG_PATH__';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: no-referrer');
function fail(int $status, string $message): never {
    // DSM replaces HTTP 5xx bodies with its HTML error page. Preserve API errors
    // in a JSON envelope so the browser can keep the last report visible.
    http_response_code($status >= 500 ? 200 : $status);
    echo json_encode(['error' => true, 'status' => $status, 'detail' => $message]);
    exit;
}
if (!is_file($configPath)) { fail(503, 'The demo is being configured.'); }
$config = json_decode((string) file_get_contents($configPath), true);
if (!is_array($config) || empty($config['key']) || empty($config['backend'])) { fail(503, 'The demo is unavailable.'); }
$route = $_GET['r'] ?? '';
$method = $_SERVER['REQUEST_METHOD'];
if (!is_string($route) || !in_array($route, ['/api/status', '/api/last', '/api/chat'], true)) { fail(404, 'Not found.'); }
if (($route === '/api/chat' && $method !== 'POST') || ($route !== '/api/chat' && $method !== 'GET')) { fail(405, 'Method not allowed.'); }
if ($method === 'POST') {
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($origin !== '' && $origin !== $config['origin']) { fail(403, 'Origin denied.'); }
    if (!str_starts_with($_SERVER['CONTENT_TYPE'] ?? '', 'application/json')) { fail(415, 'JSON required.'); }
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > 4096) { fail(413, 'Request too large.'); }
}
$body = file_get_contents('php://input', false, null, 0, 4097);
if ($body === false || strlen($body) > 4096) { fail(413, 'Request too large.'); }
$headers = [
    'Content-Type: application/json',
    'X-Demo-Gateway: ' . $config['key'],
    'X-Demo-Client: ' . ($_SERVER['REMOTE_ADDR'] ?? 'unknown'),
];
set_time_limit(100);
$context = stream_context_create(['http' => [
    'method' => $method, 'header' => implode("\r\n", $headers), 'content' => $body,
    'ignore_errors' => true, 'follow_location' => 0, 'timeout' => 90,
]]);
$result = @file_get_contents($config['backend'] . $route, false, $context);
if ($result === false) { fail(503, 'The analysis service is unavailable. Any previous report remains displayed.'); }
$status = 502;
if (preg_match('/^HTTP\/\S+\s+(\d+)/', $http_response_header[0] ?? '', $match)) { $status = (int) $match[1]; }
if ($status >= 400) {
    http_response_code(200);
    $data = json_decode($result, true);
    echo json_encode(['error' => true, 'status' => $status, 'detail' => $data['detail'] ?? 'The analysis service is unavailable.']);
} else {
    http_response_code($status);
    echo $result;
}
