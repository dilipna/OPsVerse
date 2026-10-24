import {defineConfig} from "@playwright/test";

// Browser execution is restricted to GitHub's ephemeral runner. Do not launch
// or install a browser on the user's workstation to run this suite.
if(process.env.GITHUB_ACTIONS!=="true")throw Error("Run these browser checks in GitHub Actions only");
const origin=process.env.OPSVERSE_E2E_ORIGIN||"http://127.0.0.1:3229";
if(!["http://127.0.0.1:3229","https://ops-verse.vercel.app"].includes(origin))throw Error("Unexpected browser-test origin");
export default defineConfig({
  testDir:"./tests",outputDir:"../e2e-results/artifacts",workers:1,retries:0,
  timeout:30000,globalTimeout:10*60*1000,
  reporter:[["list"],["json",{outputFile:"e2e-results/results.json"}]],
  use:{baseURL:origin,browserName:"chromium",headless:true,viewport:{width:1440,height:1000},
    trace:"retain-on-failure",screenshot:"only-on-failure"},
  webServer:origin.startsWith("http://127.0.0.1")?{
    command:"node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3229",
    url:origin+"/api/troubleshoot",reuseExistingServer:false,timeout:30000,
    env:{OPSLM_ENDPOINT:"",OPSVERSE_TROUBLESHOOT_ENDPOINT:"",NEXT_TELEMETRY_DISABLED:"1"}
  }:undefined
});
