<#
.SYNOPSIS
  관세청 국가별 수출입실적(GW) 수집기 (Windows PowerShell 5.1 / PowerShell 7 호환, 파이썬 불필요)

.DESCRIPTION
  공공데이터포털 '관세청_국가별 수출입실적(GW)' API를 국내 PC에서 호출해
  담당 54개국의 한국 기준 수출입 실적을 data\customs-kr.json 하나로 저장한다.
  - 인증키는 실행 중 화면에서 입력(에코 없음). 입력 없이 Enter 를 누르면 환경변수 DATA_GO_KR_SERVICE_KEY 사용
  - 인증키는 파일·로그·화면 어디에도 남기지 않음. 출력 파일에도 포함하지 않음
  - Encoding / Decoding 인증키 모두 사용 가능
  - 출력: UTF-8(BOM 없음) JSON. 박스에서 tools/merge_customs.py 로 country-stats.json/js 에 병합

  실행:  powershell -ExecutionPolicy Bypass -File .\fetch_customs.ps1

.PARAMETER OutFile
  출력 경로(선택). 기본값: 스크립트 위치 기준 ..\data\customs-kr.json (없으면 .\data\customs-kr.json)
#>
[CmdletBinding()]
param(
    [string]$OutFile = '',
    [string]$BaseUrl = 'https://apis.data.go.kr/1220000/nationtrade/getNationtradeList',
    [double]$DelaySeconds = 0.3
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # PS 5.1 Invoke-WebRequest 진행 표시줄로 인한 지연 방지
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

$CustomsPage = 'https://www.data.go.kr/data/15101612/openapi.do'
$Inv = [Globalization.CultureInfo]::InvariantCulture

# fetch_country_stats.py 의 COUNTRIES 와 같은 순서·코드 (ISO 2자리 = 관세청 cntyCd)
$Countries = @(
    @('RU', '러시아'),
    @('UA', '우크라이나'),
    @('KZ', '카자흐스탄'),
    @('TM', '투르크메니스탄'),
    @('UZ', '우즈베키스탄'),
    @('AZ', '아제르바이잔'),
    @('AM', '아르메니아'),
    @('MN', '몽골'),
    @('KG', '키르기스스탄'),
    @('TJ', '타지키스탄'),
    @('GE', '조지아'),
    @('MD', '몰도바'),
    @('BY', '벨라루스'),
    @('CN', '중국'),
    @('JP', '일본'),
    @('HK', '홍콩'),
    @('TW', '대만'),
    @('IN', '인도'),
    @('PK', '파키스탄'),
    @('BD', '방글라데시'),
    @('LK', '스리랑카'),
    @('NP', '네팔'),
    @('BT', '부탄'),
    @('MV', '몰디브'),
    @('AF', '아프가니스탄'),
    @('PH', '필리핀'),
    @('SG', '싱가포르'),
    @('ID', '인도네시아'),
    @('MY', '말레이시아'),
    @('VN', '베트남'),
    @('LA', '라오스'),
    @('TH', '태국'),
    @('KH', '캄보디아'),
    @('MM', '미얀마'),
    @('BN', '브루나이'),
    @('TL', '동티모르'),
    @('AE', 'UAE'),
    @('KW', '쿠웨이트'),
    @('EG', '이집트'),
    @('SA', '사우디'),
    @('IR', '이란'),
    @('IL', '이스라엘'),
    @('QA', '카타르'),
    @('OM', '오만'),
    @('BH', '바레인'),
    @('IQ', '이라크'),
    @('JO', '요르단'),
    @('TR', '튀르키예'),
    @('ZA', '남아프리카공화국'),
    @('NG', '나이지리아'),
    @('KE', '케냐'),
    @('ET', '에티오피아'),
    @('MA', '모로코'),
    @('DZ', '알제리')
)

function Say([string]$Message, [string]$Color = '') {
    if ($Color) { Write-Host $Message -ForegroundColor $Color } else { Write-Host $Message }
}

# ------------------------------------------------------------ 인증키
function Read-ServiceKey {
    Say ''
    Say '공공데이터포털 일반 인증키를 붙여넣고 Enter 를 누르세요. (Encoding/Decoding 어느 쪽이든 가능, 화면에 표시되지 않음)'
    Say '입력 없이 Enter 를 누르면 환경변수 DATA_GO_KR_SERVICE_KEY 를 사용합니다.'
    $secure = Read-Host -Prompt '인증키' -AsSecureString
    $plain = ''
    if ($secure -and $secure.Length -gt 0) {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        $secure.Dispose()
    }
    if (-not $plain) { $plain = [Environment]::GetEnvironmentVariable('DATA_GO_KR_SERVICE_KEY') }
    if ($plain) { $plain = $plain.Trim().Trim('"').Trim("'").Trim() }
    return $plain
}

# Encoding 키(%2B 등 포함)는 한 번 디코딩한 뒤, 쿼리용으로 정확히 한 번 인코딩한다.
function Get-EncodedKey([string]$Key) {
    $raw = $Key
    if ($raw -match '%[0-9A-Fa-f]{2}') { $raw = [Uri]::UnescapeDataString($raw) }
    return [Uri]::EscapeDataString($raw)
}

# ------------------------------------------------------------ 오류 안내
$GatewayCodes = @{
    '1'  = '관세청 서버 내부 오류(APPLICATION_ERROR). 잠시 후 다시 실행해 주세요.'
    '4'  = 'HTTP 오류(HTTP_ERROR). 잠시 후 다시 실행해 주세요.'
    '10' = '요청 형식 오류(INVALID_REQUEST_PARAMETER_ERROR). 스크립트 문제일 수 있습니다.'
    '12' = '해당 오픈API 서비스가 없거나 폐기됨(NO_OPENAPI_SERVICE_ERROR).'
    '20' = '서비스 접근 거부(SERVICE_ACCESS_DENIED_ERROR). 이 API에 대한 활용신청 승인 여부를 마이페이지에서 확인해 주세요.'
    '22' = '일일 호출 한도 초과(LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR). 내일 다시 실행해 주세요.'
    '30' = '등록되지 않은 인증키(SERVICE_KEY_IS_NOT_REGISTERED_ERROR). 키를 다시 복사해 붙여넣거나, 발급 직후라면 1~2시간 뒤 다시 시도해 주세요.'
    '31' = '활용기간 만료(DEADLINE_HAS_EXPIRED_ERROR). 마이페이지에서 활용기간 연장을 신청해 주세요.'
    '32' = '등록되지 않은 IP(UNREGISTERED_IP_ERROR). 활용신청 정보의 IP 설정을 확인해 주세요.'
    '33' = '서명되지 않은 호출(UNSIGNED_CALL_ERROR).'
    '99' = '기타 오류(UNKNOWN_ERROR). 잠시 후 다시 실행해 주세요.'
}
$FatalGatewayCodes = @('12', '20', '22', '30', '31', '32', '33')

# 결과 객체: Ok, Rows, Fatal(더 진행해도 소용없는 오류), Message(한국어)
function New-Result($Ok, $Rows, $Fatal, $Message) {
    return [pscustomobject]@{ Ok = $Ok; Rows = $Rows; Fatal = $Fatal; Message = $Message }
}

function Get-HttpStatus($ErrorRecord) {
    $resp = $null
    try { $resp = $ErrorRecord.Exception.Response } catch { }
    if ($resp) { try { return [int]$resp.StatusCode } catch { } }
    return 0
}

function Convert-Body([string]$Text) {
    $trim = $Text.Trim()
    if (-not $trim.StartsWith('<')) {
        if ($trim -match 'SERVICE_KEY_IS_NOT_REGISTERED|Unauthorized') {
            return New-Result $false $null $true $GatewayCodes['30']
        }
        $snippet = $trim
        if ($snippet.Length -gt 80) { $snippet = $snippet.Substring(0, 80) }
        return New-Result $false $null $false ("XML이 아닌 응답: " + $snippet)
    }
    try { [xml]$doc = $trim } catch { return New-Result $false $null $false 'XML 해석 실패(응답 형식 오류)' }

    # 공공데이터포털 게이트웨이 오류 형식
    $reason = $doc.SelectSingleNode('//returnReasonCode')
    if ($reason -and $reason.InnerText.Trim() -and $reason.InnerText.Trim() -ne '00') {
        $code = [string][int]$reason.InnerText.Trim()
        $auth = $doc.SelectSingleNode('//returnAuthMsg')
        $msg = $GatewayCodes[$code]
        if (-not $msg) { $msg = '공공데이터포털 오류 코드 ' + $code }
        if ($auth) { $msg = $msg + ' [' + $auth.InnerText.Trim() + ']' }
        return New-Result $false $null ($FatalGatewayCodes -contains $code) $msg
    }

    # 관세청 응답 형식
    $rc = $doc.SelectSingleNode('//resultCode')
    if ($rc) {
        $code = $rc.InnerText.Trim()
        if ($code -and $code -ne '00' -and $code -ne '0') {
            $rm = $doc.SelectSingleNode('//resultMsg')
            $text = ''
            if ($rm) { $text = $rm.InnerText.Trim() }
            $mapped = $null
            $num = 0
            if ([int]::TryParse($code, [ref]$num)) { $mapped = $GatewayCodes[[string]$num] }
            if ($mapped) { return New-Result $false $null ($FatalGatewayCodes -contains [string]$num) ($mapped + ' ' + $text) }
            return New-Result $false $null $false ('관세청 응답 오류 ' + $code + ': ' + $text)
        }
    }

    $rows = New-Object System.Collections.ArrayList
    foreach ($item in $doc.SelectNodes('//item')) {
        $yearNode = $item.SelectSingleNode('year')
        if (-not $yearNode) { continue }
        $period = $yearNode.InnerText.Trim()
        if ($period -notmatch '^\d{4}\.\d{2}$') { continue }   # '총계' 행 등 제외
        $vals = @{}
        $bad = $false
        foreach ($f in @('expDlr', 'impDlr', 'balPayments')) {
            $n = $item.SelectSingleNode($f)
            $v = 0.0
            if ($n -and $n.InnerText.Trim()) {
                if (-not [double]::TryParse($n.InnerText.Trim().Replace(',', ''), [Globalization.NumberStyles]::Float, $Inv, [ref]$v)) { $bad = $true }
            }
            $vals[$f] = $v
        }
        if ($bad) { continue }
        [void]$rows.Add([pscustomobject]@{
            period  = $period.Replace('.', '-')
            exports = $vals['expDlr']
            imports = $vals['impDlr']
            balance = $vals['balPayments']
        })
    }
    return New-Result $true $rows $false 'OK'
}

# 1회 조회(최대 3회 시도). 인증키가 들어간 URL은 어떤 메시지에도 넣지 않는다.
function Invoke-Customs([string]$EncodedKey, [string]$Iso2, [string]$Start, [string]$End) {
    $url = $BaseUrl + '?serviceKey=' + $EncodedKey + '&strtYymm=' + $Start + '&endYymm=' + $End + '&cntyCd=' + $Iso2
    $last = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30 -Headers @{ 'Accept' = 'application/xml,*/*' }
            $bytes = $resp.RawContentStream.ToArray()
            $text = [Text.Encoding]::UTF8.GetString($bytes)
            $result = Convert-Body $text
            if ($result.Ok -or $result.Fatal) { return $result }
            $last = $result
        } catch {
            $status = Get-HttpStatus $_
            if ($status -eq 401 -or $status -eq 403) {
                return New-Result $false $null $true ("HTTP $status - 인증키가 등록되지 않았거나 이 API 사용 승인이 아직 반영되지 않았습니다. 키를 다시 확인하거나 발급 1~2시간 뒤 다시 실행해 주세요.")
            } elseif ($status -eq 429) {
                $last = New-Result $false $null $false 'HTTP 429 - 호출이 너무 잦습니다.'
            } elseif ($status -gt 0) {
                $last = New-Result $false $null $false ("HTTP $status - 서버 오류")
            } else {
                $last = New-Result $false $null $false ('네트워크 연결 실패(' + $_.Exception.GetType().Name + '). 인터넷/회사 방화벽·프록시를 확인해 주세요.')
            }
        }
        Start-Sleep -Milliseconds ([int](1500 * $attempt))
    }
    return $last
}

function Sum-Rows($Rows, [string]$Label) {
    $e = 0.0; $i = 0.0; $b = 0.0
    foreach ($r in $Rows) { $e += $r.exports; $i += $r.imports; $b += $r.balance }
    return [ordered]@{ period = $Label; exports = $e; imports = $i; balance = $b }
}

function Row-Record($r) {
    return [ordered]@{ period = $r.period; exports = $r.exports; imports = $r.imports; balance = $r.balance }
}

# ------------------------------------------------------------ 실행
if (-not $OutFile) {
    $repoData = Join-Path (Split-Path -Parent $PSScriptRoot) 'data'
    if ((Split-Path -Leaf $PSScriptRoot) -eq 'tools' -and (Test-Path $repoData)) {
        $OutFile = Join-Path $repoData 'customs-kr.json'
    } else {
        $OutFile = Join-Path (Join-Path $PSScriptRoot 'data') 'customs-kr.json'
    }
}

$key = Read-ServiceKey
if (-not $key) {
    Say '인증키가 입력되지 않았고 환경변수 DATA_GO_KR_SERVICE_KEY 도 없습니다. 다시 실행해 주세요.' 'Red'
    exit 2
}
$encKey = Get-EncodedKey $key
$key = $null

$now = Get-Date
$thisYear = $now.Year
$lastYear = $thisYear - 1
$curYm = $now.ToString('yyyyMM', $Inv)
$ranges = @(@("$($lastYear)01", "$($lastYear)12"), @("$($thisYear)01", $curYm))

Say ''
Say ("관세청 국가별 수출입실적 수집 시작: {0}개국, 조회기간 {1}-01 ~ {2}" -f $Countries.Count, $lastYear, $now.ToString('yyyy-MM', $Inv))

$out = [ordered]@{}
$errors = [ordered]@{}
$first = $true
$failStreak = 0
$okCount = 0
$index = 0

foreach ($c in $Countries) {
    $iso2 = $c[0]; $name = $c[1]
    $index++
    $all = New-Object System.Collections.ArrayList
    $failed = $null
    foreach ($rg in $ranges) {
        $res = Invoke-Customs $encKey $iso2 $rg[0] $rg[1]
        if ($first) {
            $first = $false
            if ($res.Ok) {
                Say '인증키 확인: 정상 - 첫 호출 성공 (러시아 조회 응답 수신)' 'Green'
            } else {
                Say ('인증키/연결 확인 실패: ' + $res.Message) 'Red'
                if ($res.Fatal) {
                    Say '이 오류는 계속 진행해도 해결되지 않아 중단합니다. 파일을 만들지 않았습니다.' 'Red'
                    $encKey = $null
                    exit 3
                }
            }
        }
        if (-not $res.Ok) {
            $failed = $res
            if ($res.Fatal) {
                Say ('중단: ' + $res.Message) 'Red'
                $encKey = $null
                exit 3
            }
            break
        }
        foreach ($r in $res.Rows) { [void]$all.Add($r) }
        Start-Sleep -Milliseconds ([int](1000 * $DelaySeconds))
    }

    if ($failed) {
        $errors[$iso2] = $failed.Message
        $failStreak++
        Say ("  [{0}/{1}] {2}: 실패 - {3}" -f $index, $Countries.Count, $name, $failed.Message) 'Yellow'
        if ($failStreak -ge 5 -and $okCount -eq 0) {
            Say '연속 5개국 실패로 중단합니다. 네트워크나 인증키를 확인해 주세요. 파일을 만들지 않았습니다.' 'Red'
            $encKey = $null
            exit 4
        }
        continue
    }
    $failStreak = 0

    # 같은 월이 중복되면 마지막 값 사용 후 월 순 정렬
    $byMonth = @{}
    foreach ($r in $all) { $byMonth[$r.period] = $r }
    $months = @($byMonth.Keys | Sort-Object | ForEach-Object { $byMonth[$_] })

    $record = [ordered]@{ name = $name }
    if ($months.Count -gt 0) {
        $latest = $months[$months.Count - 1]
        $record['monthly'] = Row-Record $latest
        # 최근 12개월 합계: 최신 월부터 연속 12개월이 모두 있을 때만
        if ($months.Count -ge 12) {
            $tail = @($months[($months.Count - 12)..($months.Count - 1)])
            $ly = [int]$latest.period.Substring(0, 4); $lm = [int]$latest.period.Substring(5, 2)
            $expectStart = (New-Object DateTime $ly, $lm, 1).AddMonths(-11).ToString('yyyy-MM', $Inv)
            if ($tail[0].period -eq $expectStart) {
                $record['last12'] = Sum-Rows $tail ($tail[0].period + '~' + $latest.period)
            }
        }
    }
    $prev = @($months | Where-Object { $_.period.StartsWith("$lastYear-") })
    if ($prev.Count -eq 12) {
        $record['annual'] = Sum-Rows $prev ([string]$lastYear)
    }
    $record['months'] = @($months | ForEach-Object { Row-Record $_ })
    if ($months.Count -gt 0) {
        $out[$iso2] = $record
        $okCount++
        Say ("  [{0}/{1}] {2}: {3}개월, 최근 {4}" -f $index, $Countries.Count, $name, $months.Count, $record['monthly']['period'])
    } else {
        $errors[$iso2] = '조회 결과 없음'
        Say ("  [{0}/{1}] {2}: 조회 결과 없음" -f $index, $Countries.Count, $name) 'Yellow'
    }
}
$encKey = $null

if ($okCount -eq 0) {
    Say '수집된 국가가 없어 파일을 만들지 않았습니다.' 'Red'
    exit 4
}

$latestAll = ''
foreach ($k in $out.Keys) { $p = $out[$k]['monthly']['period']; if ($p -gt $latestAll) { $latestAll = $p } }

$doc = [ordered]@{
    schema      = 'customs-kr/1'
    generatedAt = $now.ToString('yyyy-MM-ddTHH:mm:ss', $Inv) + $now.ToString('zzz', $Inv)
    source      = [ordered]@{ name = '관세청 국가별 수출입실적(GW)'; provider = '관세청 (공공데이터포털)'; url = $CustomsPage; license = '이용허락범위 제한 없음' }
    unit        = 'USD'
    query       = [ordered]@{ from = "$($lastYear)01"; to = $curYm }
    latestPeriod = $latestAll
    countryCount = $okCount
    countries   = $out
    errors      = $errors
}

$json = $doc | ConvertTo-Json -Depth 8
$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
[IO.File]::WriteAllText($OutFile, $json + "`n", (New-Object System.Text.UTF8Encoding $false))

Say ''
Say ("완료: {0}개국 수집, 실패 {1}개국, 최근 월 {2}" -f $okCount, $errors.Count, $latestAll) 'Green'
Say ('저장 위치: ' + (Resolve-Path $OutFile).Path)
Say '이 파일 하나만 전달해 주세요. 파일에는 인증키가 들어 있지 않습니다.'
exit 0
