-- Deterministic command semantics only, not Redis integration or OOM simulation.
local M = {}
function M.new(script)
  local s = {kv={}, hash={}, publications={}, trace={}, now=100000, faults={}, script=script}
  function s:fault(command, phase, occurrence)
    self.faults[#self.faults+1] = {command=command,phase=phase or 'before',left=occurrence or 1}
  end
  function s:execute(command, ...)
    local args={...}; command=string.upper(command)
    -- Redis converts integral numeric command arguments with exact integer formatting.
    for i,v in ipairs(args) do if type(v)=='number' and v%1==0 then args[i]=string.format('%.0f',v) end end
    self.trace[#self.trace+1]={command=command,args=args}
    local fault
    for i,f in ipairs(self.faults) do
      if f.command==command then
        f.left=f.left-1
        if f.left==0 then fault=f;table.remove(self.faults,i);break end
      end
    end
    if fault and fault.phase=='before' then error('injected before '..command) end
    local out
    if command=='GET' then
      if self.hash[args[1]] then error('WRONGTYPE') end
      out=self.kv[args[1]] or false
    elseif command=='SET' then
      self.hash[args[1]]=nil; self.kv[args[1]]=tostring(args[2]);out='OK'
    elseif command=='DEL' then
      out=(self.kv[args[1]] or self.hash[args[1]]) and 1 or 0
      self.kv[args[1]]=nil;self.hash[args[1]]=nil
    elseif command=='INCR' then
      if self.hash[args[1]] then error('WRONGTYPE') end
      local n=tonumber(self.kv[args[1]] or 0)
      if not n then error('not integer') end
      n=n+1;self.kv[args[1]]=string.format('%.0f',n);out=n
    elseif command=='HMGET' then
      if self.kv[args[1]] then error('WRONGTYPE') end
      out={};local h=self.hash[args[1]] or {}
      for i=2,#args do out[#out+1]=h[args[i]] or false end
    elseif command=='HSET' then
      if self.kv[args[1]] then error('WRONGTYPE') end
      local h=self.hash[args[1]] or {};self.hash[args[1]]=h;out=0
      for i=2,#args,2 do if not h[args[i]] then out=out+1 end;h[args[i]]=tostring(args[i+1]) end
    elseif command=='PUBLISH' then
      self.publications[#self.publications+1]={channel=args[1],payload=args[2]};out=1
    elseif command=='TIME' then out={tostring(math.floor(self.now/1000)),tostring(self.now%1000*1000)}
    else error('unmodeled command '..command) end
    if fault and fault.phase=='after' then error('injected after mutation '..command) end
    return out
  end
  function s:run(...)
    KEYS={'epoch','owner','enabled','event','channel'};ARGV={...}
    for i=1,#ARGV do
      local v=ARGV[i]
      ARGV[i]=(type(v)=='number' and v%1==0) and string.format('%.0f',v) or tostring(v)
    end
    redis={call=function(...) return self:execute(...) end,
      pcall=function(...) local ok,value=pcall(self.execute,self,...);if ok then return value else return {err=value} end end}
    return assert(loadfile(self.script))()
  end
  function s:claim() return self:run('claim') end
  function s:offer(seq, opts)
    opts=opts or {}
    return self:run('offer', opts.epoch or self.kv.owner or '1',opts.kind or 'blend',seq,
      opts.base or 0,opts.chain or 'chain-A',opts.expiry or 160000,opts.issued or 100000,
      opts.ttl or 60000,opts.status or 'live',opts.payload or ('preview-'..seq))
  end
  function s:snapshot(floor,status) return self:run('snapshot',floor or 0,status or 'live') end
  return s
end
return M
