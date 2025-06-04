import { graphql, Link, PageProps } from "gatsby";
import React, { useEffect, useMemo, useState } from "react";
import { Button, Radio, Switch, Table } from "antd";
import { QueryStateOpts, useQueryState } from "use-location-state";

import LayoutWrapper from "../components/layout";
import BuildTimeFooter from "../components/time";
import Title from "../components/title";
import TestCase from "../components/case";
import StatsPane from "../components/stat";
import { SiteDisplayRoot } from "../interface";
import rawData from "../data.json";

const displayData = rawData as SiteDisplayRoot;

export const query = graphql`
  {
    site {
      buildTime
    }
  }
`;

type DataProps = {
  site: {
    buildTime: string;
  };
};


enum ReleaseTestOption {
  NoReleaseTest = 1,
  Mixed = 2,
  OnlyReleaseTest = 3
}

const regex = /DataCaseName-(.+)-END/;

const App: React.FC<PageProps<DataProps>> = ({ data, location }) => {
  const [showAll, setShowAll] = useQueryState<boolean>("showAll", false);
  const [ownerSelection, setOwnerSelection] = useState<string>("all");
  const [githubData, setGitHubData] = useState<Map<string, any>>(new Map());
  const [releaseTestOption, setReleaseTestOption] = useState<ReleaseTestOption>(ReleaseTestOption.NoReleaseTest);

  useEffect(
    () => {
      setOwnerSelection(new URLSearchParams(location.search).get("owner") || "all")
    }
  );


  useMemo(
    () => fetch("https://api.github.com/repos/ray-project/ray/issues?labels=flaky-tracker&state=all&per_page=100")
      .then(resp => resp.json())
      .then(data => {
        console.log(data)
        const newData = new Map<string, any>(data.map(issue => [issue.body.match(regex)?.at(1), { url: issue.html_url, state: issue.state }]));
        setGitHubData(newData);
      }),
    []
  );


  const { dataSource, columns } = JSON.parse(displayData.table_stat);
  
  let testsToDisplay = displayData.failed_tests;
  testsToDisplay = testsToDisplay.filter(
    (c) => ownerSelection === "all" || ownerSelection === c.owner
  );

  if (releaseTestOption == ReleaseTestOption.OnlyReleaseTest) {
    testsToDisplay = testsToDisplay.filter(t => t.name.indexOf("release://") > 0);
  } else if (releaseTestOption == ReleaseTestOption.NoReleaseTest) {
    testsToDisplay = testsToDisplay.filter(t => t.name.indexOf("release://") == -1);
  }

  let numHidden = 0;
  if (!showAll) {
    numHidden = testsToDisplay.length - 100;
    testsToDisplay = testsToDisplay.slice(0, 100);
  }


  return (

    <LayoutWrapper>
      <Title></Title>

      <StatsPane stats={displayData.stats}></StatsPane>

      <Table
        dataSource={dataSource}
        columns={columns}
        size={"small"}
        pagination={false}
      ></Table>

      <Radio.Group
        style={{ paddingTop: "1%" }}
      >
        <Link to={"/?owner=all"}><Radio.Button value="all">team:all</Radio.Button></Link>
        {displayData.test_owners.map((owner) => (
          <Link to={"/?owner=" + owner} key={owner}>
            <Radio.Button value={owner}>
              {owner}
            </Radio.Button>
          </Link>
        ))}
      </Radio.Group>

      {"     "}
      {"Show Release Tests"}
      {"     "}
      <Radio.Group onChange={e => setReleaseTestOption(e.target.value)} defaultValue={ReleaseTestOption.NoReleaseTest}>
        <Radio.Button value={ReleaseTestOption.NoReleaseTest}>No</Radio.Button>
        <Radio.Button value={ReleaseTestOption.Mixed}>Yes</Radio.Button>
        <Radio.Button value={ReleaseTestOption.OnlyReleaseTest}>Only</Radio.Button>
      </Radio.Group>



      {testsToDisplay.map((c) => (
        <TestCase key={c.name} case={c} compact={false} githubState={githubData}></TestCase>
      ))}

      {numHidden > 0 && (
        <Button
          style={{ margin: "12px" }}
          type={"primary"}
          onClick={() => {
            setShowAll((val) => !val);
          }}
        >
          {showAll
            ? "Hide additional tests"
            : `Show all failed tests (${numHidden} hidden, it will take ~2s to load) `}
        </Button>
      )}

      <BuildTimeFooter
        buildTime={Date.parse(data.site.buildTime)}
      ></BuildTimeFooter>
    </LayoutWrapper>
  );
};

export default App;
