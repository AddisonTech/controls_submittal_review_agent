# Test set v2 holdout (pinned)

These 10 cases are the v2 holdout. They were split off when the set was generated, before any
engine ran on any v2 case. Every v2 tool refuses a holdout folder unless it is run as
`tools\validate_v2.py --holdout-final`, which scores each engine on the holdout exactly once.

The files are pinned by SHA-256. A file that does not match its pin stops the final run.

Generator: tools/make_v2_sets.py 2.0.0

Scorer: tools/score_v2.py sha256 `6dd9976119a30dd1fe4e59bf7a15444ec0dcb8d76524fe4ca6945611196e55c3`

| case | file | sha256 |
|---|---|---|
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/seeded/spec.txt | `bae9a3022c77f3fc6064fcd442da79c92e6993b4a563b71532332deb79c0a476` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/seeded/submittal_sequence.txt | `98806a59dfe1af6db8f729618347ef2826a87ff3ed9e7b1851a3a5cfe2541acc` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/seeded/submittal_points.csv | `58bb13aeff8bd416bac291da17ac8ca51172cd004f9b2747bfcdedd51199a891` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/seeded/drawing_list.csv | `9283a4f0041ff9f92a2a55c9af615d78acf2e8392d095add3fffccc82447ee26` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/seeded/labels.json | `033220dc718b15025f0deecbf1dcfbd39672c2192ea994054c9d6379741be617` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/clean/spec.txt | `bae9a3022c77f3fc6064fcd442da79c92e6993b4a563b71532332deb79c0a476` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/clean/submittal_sequence.txt | `05ffc65917e9545ec26b2a638d5fa4f7e2cbfbe7b03d1251ab6bab5848cafeb5` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/clean/submittal_points.csv | `58bb13aeff8bd416bac291da17ac8ca51172cd004f9b2747bfcdedd51199a891` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/clean/drawing_list.csv | `9283a4f0041ff9f92a2a55c9af615d78acf2e8392d095add3fffccc82447ee26` |
| v2c04_chw_plant | validation/v2/holdout/v2c04_chw_plant/clean/labels.json | `f519fd5cc99e791fe8669d94ff8215b3b90c6847fce433364b4e30347cefa896` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/seeded/spec.txt | `692a5db8fe4d45ca9a291813eff7134c5bc27254ab6c05bba58d578240ed9184` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/seeded/submittal_sequence.txt | `2567624aeaf6ed90fe264e5660d24993723ef50364eee78a3fb931a1cd21c7d5` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/seeded/submittal_points.csv | `2f05e29401589a9c87fab2cf88df3c94b6d20cab49368e940c93e77c0f158e0d` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/seeded/drawing_list.csv | `dd50ee74f72442892b39734735dc18cc4426643d3fd122f52b61aaa19d4ee2e1` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/seeded/labels.json | `12ed4cb9f42156670eb2ffc4018d67fa4247d260037f0cdbf5fd5b374b22ac1a` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/clean/spec.txt | `692a5db8fe4d45ca9a291813eff7134c5bc27254ab6c05bba58d578240ed9184` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/clean/submittal_sequence.txt | `1eb395344f242bc6f6a26a2db0054fdac8753bb96992b1a84de81ffaa93e876f` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/clean/submittal_points.csv | `2f05e29401589a9c87fab2cf88df3c94b6d20cab49368e940c93e77c0f158e0d` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/clean/drawing_list.csv | `dd50ee74f72442892b39734735dc18cc4426643d3fd122f52b61aaa19d4ee2e1` |
| v2c08_vav_rh | validation/v2/holdout/v2c08_vav_rh/clean/labels.json | `e2311c44151d6a90fca2e84a0f94a8333a520ad666954a0c9786b73dea2c1074` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/seeded/spec.txt | `6445f7304cc6444c72b441e506c3676e579ce16f4a547cb56a86f155c57e68a3` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/seeded/submittal_sequence.txt | `2bf59bbb25e2a02ad98d5f87e27dfbecf649791c012be5c3877d82b2a881bbc9` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/seeded/submittal_points.csv | `75f703857e3539a4c4f02decca7a5662628caddfe9ef0c2680c35c148b395e21` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/seeded/drawing_list.csv | `738bfc6371b39132bd05bf3a32fcd7700568ac4549be63e729f95ca5031f915c` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/seeded/labels.json | `5228eda30d64a673b6ecb8a6fae3eb25c1d13a9b756b714ab96bf8e326a2d82a` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/clean/spec.txt | `6445f7304cc6444c72b441e506c3676e579ce16f4a547cb56a86f155c57e68a3` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/clean/submittal_sequence.txt | `0d191be9d733e745eeae0ea2866d842ee8aca8b8dc2dc002e908de8022570a16` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/clean/submittal_points.csv | `c3388ce2718544b4af2ace2dd89b480d58aa139f3763ea72b6dd1329620729d1` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/clean/drawing_list.csv | `1364a1b3922b6eb46ee7f952592f9f4333254729d81dab6a6f4ec66f3987a082` |
| v2c12_hw_plant | validation/v2/holdout/v2c12_hw_plant/clean/labels.json | `0e867736baa3cd3e3420662a42e07c6bedced4fad0e7f38fb92504318ce667a0` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/seeded/spec.txt | `ce1201adb94ed9482bb821b75c6ad6f92193a44dc1f9bcf3b6dffa57c2bf5419` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/seeded/submittal_sequence.txt | `6983620dad798ad6f060ddcdfa5a60fa7d5a07690a52b27ea8e1e4bd43815583` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/seeded/submittal_points.csv | `b4202dad89f4d93a57f43e693342098f6f78e50b6b2e65e9da3e648052af14b6` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/seeded/drawing_list.csv | `03b0433999fd10244226d56916851d9a007259f9b8b917b59f43be856b7d7af4` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/seeded/labels.json | `a0a3535e2e572bf376e8e3a74d91f5adbddd8d614198aa38c006e9f686152d2f` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/clean/spec.txt | `ce1201adb94ed9482bb821b75c6ad6f92193a44dc1f9bcf3b6dffa57c2bf5419` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/clean/submittal_sequence.txt | `3c0c933deb0280767bc81b797a85386de19cc1eda146055bce9506c2834efccb` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/clean/submittal_points.csv | `319fba41a85496c650ca57041b95e3986490d34541bcc75923994ed882963e44` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/clean/drawing_list.csv | `2b7118536d202ae5885f0ec857eb1cad52c0c2c043d244dbdc270c7b5fed9de8` |
| v2c16_chw_plant | validation/v2/holdout/v2c16_chw_plant/clean/labels.json | `9f6a40d22478a76c316844a2a04e3a0424d3d854265d3732b48fb44646b18334` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/seeded/spec.txt | `bce24493f222e1d515cc6bfeafb72350423aae3d6c3beb06247486b0091337a1` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/seeded/submittal_sequence.txt | `90162bfc3f74bd68d5bbdd3b4637466d045cd019e8999147d9a9c50c3931449b` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/seeded/submittal_points.csv | `e91b4af12d509f7f91c5d0b1dfbbf4a773473ec15efacedb52e0f20c6747f99a` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/seeded/drawing_list.csv | `8675aeecae018dd4f9685dcfa4f5e309a0c7402b455762b833652dcbf0c52eb8` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/seeded/labels.json | `50237c2d3be586f6fed5ab5d0e59ed1cef243b1652bc20587e91883fe2bbe36e` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/clean/spec.txt | `bce24493f222e1d515cc6bfeafb72350423aae3d6c3beb06247486b0091337a1` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/clean/submittal_sequence.txt | `6499e62717e0c9711346789a58afcbef8b449a6591d50d2542d2cfd4004dad99` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/clean/submittal_points.csv | `70c2063b78b98de9db91dbeaaf5d7620d97807bd7cdb2a14bf7f9cd16858f0ad` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/clean/drawing_list.csv | `8675aeecae018dd4f9685dcfa4f5e309a0c7402b455762b833652dcbf0c52eb8` |
| v2c20_vav_rh | validation/v2/holdout/v2c20_vav_rh/clean/labels.json | `3a44c05aed2a3b2c4b269e1f27fe91afd3e4b87d887cd14d263e89348a8faf14` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/seeded/spec.txt | `e8831de2dd48280e340f8ec6ff080545115137a8072e2a4f1f0c2451fba5addc` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/seeded/submittal_sequence.txt | `18e23edeecfea6f8dfb9fe40216358a9f658944974ef6d5e69f90a618e518f6d` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/seeded/submittal_points.csv | `afca28b6856efc580b5cf6fd14dceb958afa5affbdc1b80c1159363ce498c0c9` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/seeded/drawing_list.csv | `5589067c44de7bc3a69639e6de22433fb8890e00a928c78a567a70b1d548b8d1` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/seeded/labels.json | `6ee6298a0b64bb9649f7c99277aba06aa4e9974506ab08c2ded1015a75ea8f31` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/clean/spec.txt | `e8831de2dd48280e340f8ec6ff080545115137a8072e2a4f1f0c2451fba5addc` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/clean/submittal_sequence.txt | `0cb438855a9281e2c0770349f227a75642a6640ce6ecb03ae4d1d3c6497bfc12` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/clean/submittal_points.csv | `858bf65b71b913cc623c5695e577c08462944045013e5975ab61a010e43ace9b` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/clean/drawing_list.csv | `5589067c44de7bc3a69639e6de22433fb8890e00a928c78a567a70b1d548b8d1` |
| v2c24_hw_plant | validation/v2/holdout/v2c24_hw_plant/clean/labels.json | `329c52ef9c6505266c639fdbee2e59cf0e61f4a27490897116f7705a71462290` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/seeded/spec.txt | `e79d42d12e50f111e24b48dfc19a18868108bee599b214255880df7874106898` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/seeded/submittal_sequence.txt | `7c8ac3ad143e8abf18c6aac160c3d92a0bec05e0cd34b8684a95ce7ad2ef8d04` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/seeded/submittal_points.csv | `1bff576ac7df2cc7a76081d455c64a3c1dbf9c6b31962197147577b4ec54c01a` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/seeded/drawing_list.csv | `7ae3e98ba60431b9e64772a256b910375482efbb1e81d594b2547862bff1f089` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/seeded/labels.json | `f6d057de7a300ed9c34c0068d30f5766729e861a9a7331babc011aa47c1cdb71` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/clean/spec.txt | `e79d42d12e50f111e24b48dfc19a18868108bee599b214255880df7874106898` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/clean/submittal_sequence.txt | `6fb5036c8403f4d65026527fb4f4b6260661a6f34cee29409f8bd4d0388439f3` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/clean/submittal_points.csv | `d76123a4a55064d673ddd9f1f2089fd20197ed3e34f3a8f5fd0ccbfef23aa0e9` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/clean/drawing_list.csv | `7ae3e98ba60431b9e64772a256b910375482efbb1e81d594b2547862bff1f089` |
| v2c28_chw_plant | validation/v2/holdout/v2c28_chw_plant/clean/labels.json | `d9319bef91fa50084cbd6937fe0baa51ba307e8ded1cfee268f61dd589b958a7` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/seeded/spec.txt | `d806abe876e48685641a95a1f60f3dd495f1463658cfdc07a2ef7a72509eec4a` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/seeded/submittal_sequence.txt | `8cdfd9c8f6e7cfc9011befe4d4a57d2945ed857e7f3debc7cd81cc0e80eba09d` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/seeded/submittal_points.csv | `29b7b67d95bf950dda63bf4a3b64652a75a3131110d8330a314e9bf843dcfa9e` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/seeded/drawing_list.csv | `482784a227ff789a584249a9bf890abff01c47b39efc4b40e0f5191c73bbcdc7` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/seeded/labels.json | `5f1ad44c37040c9fa346e6f18079f4c6401b2515f1baa6e69d3acdc1d3e45692` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/clean/spec.txt | `d806abe876e48685641a95a1f60f3dd495f1463658cfdc07a2ef7a72509eec4a` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/clean/submittal_sequence.txt | `ce1b240ac3dc9395986cb8bf31ca8d4e595218cde7554fc07c18cb568811dd2f` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/clean/submittal_points.csv | `faef84ad6d58db428ffe6bd1b463b7456ef33c3e9724632c9d41bb14d7a06314` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/clean/drawing_list.csv | `482784a227ff789a584249a9bf890abff01c47b39efc4b40e0f5191c73bbcdc7` |
| v2c32_vav_rh | validation/v2/holdout/v2c32_vav_rh/clean/labels.json | `16bf72c4e5d508adc56084fcb43ea3973a2c62dea5adc99f0d6d99b1893653c1` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/seeded/spec.txt | `7e1aac368c30bfa4d89cc7cdb18e7af1d6db7a568a7f9a192854bd56fa772a71` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/seeded/submittal_sequence.txt | `13db6e369a5218969f60809d5b062788e0d638bcde96a572255d434e8d48cbd5` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/seeded/submittal_points.csv | `14ddbcc6c216be541bd7c5509c29592d46ab6c0a99d5699b74ace14f4b5bad44` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/seeded/drawing_list.csv | `e92b7e59876c17060108ecc2d2a8adcfd406f42bbac1af0641a9bda1dfb75a67` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/seeded/labels.json | `53b56b1b6b7b35017411e030e8f90e9760c6ddf1aa8813c14f0872056a95dba6` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/clean/spec.txt | `7e1aac368c30bfa4d89cc7cdb18e7af1d6db7a568a7f9a192854bd56fa772a71` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/clean/submittal_sequence.txt | `7616bfa29155c807548c2072ce26dc1ae4d1ed42d92232d9b7220f1380f1f569` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/clean/submittal_points.csv | `4d5236a4d60310e6fd962f5d2f95572ffac07075dce06b6666ca23eb35af0a2b` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/clean/drawing_list.csv | `e92b7e59876c17060108ecc2d2a8adcfd406f42bbac1af0641a9bda1dfb75a67` |
| v2c36_hw_plant | validation/v2/holdout/v2c36_hw_plant/clean/labels.json | `ad93508022d58af7206b035870517ab42ccf0447384a6703ab45d8840bfb56f8` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/seeded/spec.txt | `2476fcf897df6a372d9ea99a62324e36ceef08265f386117426aa18ee38f7fa9` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/seeded/submittal_sequence.txt | `55b2993a200e122b6f4081fce5b5bf31a18163a582e566d934e493a638dcddef` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/seeded/submittal_points.csv | `d47dce8a387732d898e25d789b1e156259cb83eb366fd90d036d8989dd51084b` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/seeded/drawing_list.csv | `93422c24f43e283200bee2eb2043c7803f3990b422436acb2c0aebdc5c79d760` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/seeded/labels.json | `3ed596ad69ff1cbfa61d3f7e484347ffd150f7080ea531dc9647c2b0178d01c8` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/clean/spec.txt | `2476fcf897df6a372d9ea99a62324e36ceef08265f386117426aa18ee38f7fa9` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/clean/submittal_sequence.txt | `0b9e8d8cffa83ebf89789acdf44bb05b9364963651c5636e94f8756ffabec8c1` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/clean/submittal_points.csv | `1a703ef23d6e564438ad2b6d9879861a4ed4a25bdc4f8bf72cd704c75ce6a65b` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/clean/drawing_list.csv | `93422c24f43e283200bee2eb2043c7803f3990b422436acb2c0aebdc5c79d760` |
| v2c40_ahu_mz | validation/v2/holdout/v2c40_ahu_mz/clean/labels.json | `58f04c61a051a0f584cb7f4e58addf938eb9ca9708e26aa6b2e2677142034bc6` |
