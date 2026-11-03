<!--
PUBLISH VIA DJANGO ADMIN -> Blog -> Posts -> Add post
  Title:  Renting a Front Door: Exposing My Homelab Without Opening a Port
  Tags:   homelab, kubernetes, k3s, networking, security, wireguard, traefik, self-hosting, gitops
  Status: Published
Paste everything below this comment into the Body field. (HTML comments don't render.)
-->

The normal way to put a self-hosted thing on the internet is to forward ports 80 and 443 from your home router to whatever's serving them. It works fine. I just didn't want it. Forwarding those ports puts my home IP address in public DNS where anyone can look it up, and it leaves a permanent hole in my router pointing straight at my cluster. Neither of those sat well with me.

So the public face of my homelab isn't my house at all. It's a $5 VPS that holds the public IP and tunnels back to me over WireGuard. My home router has zero inbound ports open. Not 443, not 80, nothing. This post is less about how I set that up and more about why, because the tradeoffs turned out to be the interesting part.

## How it actually works

Every public hostname I serve (the apex domain, the dev and qa environments, the `*.review` wildcards) points in DNS at a small DigitalOcean droplet instead of at me. The droplet barely does anything. It takes inbound 80 and 443 and shoves the raw TCP straight down a WireGuard tunnel to my home gateway, which hands it off to Traefik in the cluster. Traefik terminates TLS and routes to whatever app you asked for.

The tunnel is boring, which is the point. It's just a WireGuard client on my UniFi gateway dialing the droplet on one UDP port:

```ini
# home gateway to VPS, roughly
[Peer]
PublicKey  = <droplet-public-key>
Endpoint   = <droplet-ip>:51820
AllowedIPs = 10.12.12.1/32
```

And the droplet's whole job is about ten lines of stream proxy. Conceptually:

```text
# inbound 443 on the public IP, sent straight down the tunnel, untouched
443  ->  10.12.12.2:443   (TCP passthrough, no TLS termination)
 80  ->  10.12.12.2:80
```

That's the entire machine. It doesn't know what apps I run, it doesn't hold a single certificate, and it never decrypts anything. It just moves bytes around.

## Why bother, instead of forwarding a port?

The decision that mattered wasn't how to build this. It was where to put the trust boundary. I put it at home, on purpose, and pretty much everything I like about this setup falls out of that one call.

Start with TLS. Certificates are issued and held by cert-manager inside the cluster, so TLS terminates at home. The droplet only ever sees ciphertext. It's doing plain layer-4 passthrough, so it physically can't read what's flowing through it or steal a key it was never handed. If somebody roots my droplet tonight, what do they actually get? A dumb pipe. Not my data, not my certs, and no real foothold in my network beyond a tunnel that goes exactly one place. A box I'm renting from strangers is exactly the box that should be holding nothing worth taking.

There's a small thing here I didn't appreciate until I watched it happen: even the Let's Encrypt challenges come in over the tunnel. The HTTP-01 check lands on port 80, travels the same path as real traffic, hits Traefik, and gets answered. Nothing is special-cased. There's one way in, and it's the tunnel.

Then there's my home IP, which is now just not on the internet. DNS points at the droplet, so if you scan my actual home connection you find nothing. No open ports, no banner, no sign anything is hosted here at all. The thing getting poked and scanned all day is the throwaway box, not the place I live.

WireGuard is the right tool for the spine, too. One UDP port between two machines I own, fast because it lives in the kernel, and quiet in a way an open 443 just isn't. Funny enough, it's not the tunnel I use everywhere. The one carrying my torrent traffic to a commercial VPN is OpenVPN, only because that provider doesn't do WireGuard. Picking the right tunnel for each job beats forcing one tool to do everything, which is apparently a lesson I enjoy relearning.

The front-end stays dumb on purpose. All the actual brains (ingress rules, TLS, cert-manager, routing, the app definitions themselves) live in the cluster under GitOps, where I already manage them. The droplet has no opinions about any of it. If it died, I could rebuild the public front-end in a few minutes and lose nothing, because nothing important was ever there to begin with.

## What it costs me

I'd be lying if I sold this as free, so here's the bill.

Every public byte takes a detour now. All the inbound traffic flows home through one little VPS, so its bandwidth, its location, and the extra hop are my public ceiling. For a personal site and a handful of dashboards I never notice it. If I were streaming video to strangers, I absolutely would.

It's also a single point of failure for the public side. If the droplet or the tunnel goes down, nobody outside can reach my apps, even though everything is still running happily at home and works fine on the LAN. I traded "exposed house" for "dependent front door." That's a real tradeoff, not a freebie, and worth saying out loud.

Here's the part I'm least proud of. The droplet is the one corner of all this that isn't GitOps. The whole cluster is declarative: every app, every cert, every firewall rule is a diff somebody could review. But the VPS proxy and its WireGuard config live on the droplet itself, hand-maintained, backed up by nothing but my memory. It's the one seam where the tidy story leaks. Codifying it with a bit of Terraform and cloud-init is the obvious next step, and honestly writing this is mostly me admitting I haven't done it.

I'm also still handing a provider my metadata. They can't read the traffic, but they can see that it exists, where it's coming from, and roughly how much there is. Encrypting at home moves the boundary. It doesn't make the box disappear.

## The same idea, twice

I closed the last ports on my router around the same time I moved my torrent client behind a VPN, and afterward I realized they were the same move in different clothes. The instinct both times was: don't guard an exposure, relocate it. Forwarding 443 from my router guards a hole. Renting a front door deletes the hole and parks the exposure somewhere disposable and off-site that holds nothing. Closing 80 and 443 at home wasn't even a separate task. It just fell out of the front door no longer being my house.

## What I'd tell past me

A few things I keep coming back to.

Pick where your trust boundary goes first, then let the architecture serve it. "TLS terminates at home" is one short sentence, and it's the whole reason a compromised front-end is a shrug instead of an incident.

Keep the exposed thing dumb and disposable. The less your public surface knows, the less it can leak, and the easier it is to throw away.

"No open ports" isn't free. You pay for it with a hop and a dependency. Worth it for me, but say the price out loud before you copy the pattern.

And codify even the boring edges. The one machine I left out of version control is, of course, the one I'd be most annoyed to lose the config for. Don't be me. Or at least, don't be me for as long as I have been.

My router's inbound list is empty, my home IP isn't in anyone's DNS, and the only thing facing the internet is a machine I could throw in the bin and rebuild before lunch. For the cost of one network hop and five bucks a month, that feels like a pretty good front door.
