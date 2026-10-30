/* Ordered SSE state, including snapshot races, missing events and restarts. */
export class StateFeed {
  constructor({fetchSnapshot, snapshot, change, retryMs=1000, maxPending=1000}) {
    Object.assign(this,{fetchSnapshot,snapshot,change,retryMs,maxPending});
    this.version=0; this.highest=0; this.generation=0; this.pending=new Map();
  }
  reset(snapshot) {
    this.stop(); this.closed=false; this.repairing=false;
    this.version=snapshot._version || 0; this.highest=this.version;
    this.snapshot(snapshot);
  }
  stop() {
    ++this.generation; this.closed=true;
    clearTimeout(this.timer); this.timer=null; this.pending.clear();
  }
  receive(message) {
    if(this.closed || message.v<=this.version) return;
    this.highest=Math.max(this.highest,message.v);
    this.pending.set(message.v,message);
    if(this.pending.size>this.maxPending) this.pending.clear();
    this.drain();
    if(this.version<this.highest) this.repair();
  }
  drain() {
    while(this.pending.has(this.version+1)) {
      const message=this.pending.get(++this.version);
      this.pending.delete(this.version); this.change(message);
    }
    if(this.version>=this.highest) {clearTimeout(this.timer);this.timer=null;}
  }
  async repair() {
    if(this.closed || this.repairing) return;
    this.repairing=true;
    clearTimeout(this.timer);this.timer=null;
    const generation=this.generation;
    try {
      const snapshot=await this.fetchSnapshot();
      if(generation!==this.generation || this.closed) return;
      // Updates may have filled the gap while this request was in flight.
      if(snapshot._version>=this.version) {
        this.version=snapshot._version;
        this.highest=Math.max(this.highest,this.version);
        this.snapshot(snapshot);
        for(const v of this.pending.keys()) if(v<=this.version) this.pending.delete(v);
        this.drain();
      }
    } catch (_) {
      // Keep the last coherent state and retry even if no more events arrive.
    } finally {
      if(generation===this.generation && !this.closed) {
        this.repairing=false;
        if(this.version<this.highest) this.timer=setTimeout(()=>this.repair(),this.retryMs);
      }
    }
  }
}
